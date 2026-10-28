import os
import glob
import io
import time
import json
from datetime import datetime, timedelta
from google import genai
from google.genai import types
from PIL import Image


def get_latest_image():
    """Szuka najnowszego pliku graficznego w folderze img_tmp"""
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
    files = []
    for ext in image_extensions:
        files.extend(glob.glob(f"img_tmp/{ext}"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def get_history_data(file_path="odczyty24h.txt"):
    """Pobiera dane historyczne i przygotowuje etykiety oraz wartości do wykresu"""
    labels = []
    values = []

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or " | " not in line:
                    continue
                try:
                    parts = line.split(" | ")
                    date_str = parts[0]
                    val_str = parts[1]

                    # Formatujemy datę do krótkiej formy na oś X (np. 18:35)
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    short_date = dt.strftime("%H:%M")

                    labels.append(short_date)
                    values.append(float(val_str))
                except (ValueError, IndexError, TypeError):
                    continue
    return labels, values


def clean_and_update_history(new_value, file_path="odczyty24h.txt"):
    """Zapisuje nowy odczyt i usuwa wpisy starsze niż 24 godziny"""
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    updated_lines = []

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parts = line.split(" | ")
                    date_part = parts[0]
                    entry_time = datetime.strptime(date_part, "%Y-%m-%d %H:%M:%S")
                    if entry_time >= cutoff_time:
                        updated_lines.append(line)
                except (ValueError, IndexError, TypeError):
                    continue

    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    new_entry = f"{timestamp} | {new_value}"
    updated_lines.append(new_entry)

    with open(file_path, "w", encoding="utf-8") as range_file:
        for line in updated_lines:
            range_file.write(line + "\n")


def optimize_image(image_path, max_size=1024):
    """Zmniejsza wagę pliku i rozdzielczość, aby uniknąć rozłączania API"""
    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        return img_byte_arr.getvalue()


def update_html(timestamp, value, image_path, success=True, file_path="index.html"):
    """Aktualizuje plik index.html nowymi danymi, statusem oraz wykresem Chart.js"""
    cache_buster = int(time.time())
    img_src = f"{image_path}?t={cache_buster}"

    uwaga_html = ""
    if not success:
        uwaga_html = '<div class="uwaga">Ostatni odczyt się nie powiódł, wyświetlana jest poprzednia poprawna wartość.</div>'

    # Pobieramy oczyszczone dane z historii
    labels, values = get_history_data()

    html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Podgląd Licznika Gazu</title>
    <!-- Dołączenie biblioteki Chart.js z CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f4f9;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 550px;
            width: 100%;
            margin: 20px;
        }}
        h1 {{ color: #333; font-size: 24px; margin-bottom: 10px; }}
        h3 {{ color: #444; font-size: 16px; margin-top: 25px; margin-bottom: 10px; }}
        .status {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
        .timestamp {{ font-weight: bold; color: #2c3e50; }}
        .odczyt {{ font-size: 32px; font-weight: bold; color: #27ae60; background: #e8f8f5; padding: 10px; border-radius: 10px; margin: 20px 0;
