import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, g
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime
from sklearn.linear_model import LinearRegression
import numpy as np

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), 'budget.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        amount REAL,
        category TEXT
    )""")
    db.commit()

# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            df = pd.read_csv(filepath)
            for _, row in df.iterrows():
                db.execute(
                    'INSERT INTO expenses (date, amount, category) VALUES (?, ?, ?)',
                    (row['date'], row['amount'], row['category'])
                )
            db.commit()
            return redirect(url_for('index'))  # redirect to refresh page

    # List files in upload folder
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith('.csv')]
    return render_template('index.html', files=files)

@app.route('/forecast_file/<filename>')
def forecast_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return "File not found", 404

    df = pd.read_csv(filepath)

    if df.empty:
        return render_template('forecast.html', forecast=None, forecast_plot=None, year=None, month=None)

    # convert and group as in /forecast
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    grouped = df.groupby('category')['amount'].sum().reset_index()
    forecast_result = dict(zip(grouped['category'], grouped['amount'].round(2)))

    # pie chart
    fig, ax = plt.subplots()
    ax.pie(grouped['amount'], labels=grouped['category'], autopct='%1.1f%%', startangle=90)
    ax.set_title(f"Spending Breakdown in {filename}")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    forecast_plot = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    return render_template('forecast.html', forecast=forecast_result, forecast_plot=forecast_plot, year=None, month=None)


@app.route('/dashboard')
def dashboard():
    db = get_db()
    df = pd.read_sql_query('SELECT * FROM expenses', db)
    if df.empty:
        return render_template('dashboard.html', data_available=False)

    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M')
    grouped = df.groupby(['month', 'category'])['amount'].sum().unstack().fillna(0)

    fig, ax = plt.subplots(figsize=(10, 5))
    for category in grouped.columns:
        ax.plot(grouped.index.astype(str), grouped[category], marker='o', label=category)

    ax.set_title("Monthly Spending per Category")
    ax.set_xlabel("Month")
    ax.set_ylabel("Amount")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    line_chart = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    return render_template('dashboard.html', data_available=True, line_chart=line_chart)

@app.route('/forecast', methods=['GET'])
def forecast():
    db = get_db()
    df = pd.read_sql_query('SELECT * FROM expenses', db)

    if df.empty:
        return render_template('forecast.html', forecast=None, forecast_plot=None, year=None, month=None)

    # Get selected year and month from query
    try:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
    except ValueError:
        year = datetime.now().year
        month = datetime.now().month

    # Parse date
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])

    # Filter by selected month and year
    filtered = df[(df['date'].dt.year == year) & (df['date'].dt.month == month)]

    if filtered.empty:
        return render_template('forecast.html', forecast=None, forecast_plot=None, year=year, month=month)

    # Group by category and sum
    grouped = filtered.groupby('category')['amount'].sum().reset_index()

    # Build forecast result
    forecast_result = dict(zip(grouped['category'], grouped['amount'].round(2)))

    # Plot pie chart
    fig, ax = plt.subplots()
    ax.pie(grouped['amount'], labels=grouped['category'], autopct='%1.1f%%', startangle=90)
    ax.set_title(f"Spending Breakdown for {year}-{month:02d}")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    forecast_plot = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    return render_template('forecast.html', forecast=forecast_result, forecast_plot=forecast_plot, year=year, month=month)


@app.route('/history')
def history():
    db = get_db()
    df = pd.read_sql_query('SELECT * FROM expenses ORDER BY date DESC LIMIT 20', db)
    return render_template('history.html', records=df)

# --- Start App ---
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
