import os
import re
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


def normalize_reading(raw):
    """
    Wyciąga cyfry z odpowiedzi modelu i zwraca stan w formacie XXX.YYY.
    Zwraca None, jeśli liczba cyfr jest inna niż 6 (odczyt niepewny).
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) != 6:
        return None
    return f"{digits[:3]}.{digits[3:]}"


def get_history_data(file_path="odczyty24h.txt"):
    """Pobiera dane historyczne i przygotowuje dane dla obu wykresów (stan i zużycie chwilowe)"""
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

                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    short_date = dt.strftime("%H:%M")

                    labels.append(short_date)
                    values.append(float(val_str))
                except (ValueError, IndexError, TypeError):
                    continue

    # Obliczanie różniczki (chwilowego zużycia)
    consumption_labels = []
    consumption_values = []

    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        # Zabezpieczenie przed ujemnymi wartościami (np. w przypadku resetu licznika lub korekty)
        if diff < 0:
            diff = 0.0

        # Zaokrąglenie do 3 miejsc po przecinku, aby uniknąć błędów zmiennoprzecinkowych
        diff = round(diff, 3)

        consumption_labels.append(labels[i])
        consumption_values.append(diff)

    return labels, values, consumption_labels, consumption_values


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
    """Aktualizuje plik index.html dwoma wykresami liniowymi Chart.js (stan i zużycie chwilowe)"""
    cache_buster = int(time.time())
    img_src = f"{image_path}?t={cache_buster}"

    uwaga_html = ""
    if not success:
        uwaga_html = '<div class="uwaga">Ostatni odczyt się nie powiódł, wyświetlana jest poprzednia poprawna wartość.</div>'

    # Pobieramy serie danych dla obu wykresów
    labels, values, diff_labels, diff_values = get_history_data()

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
        .odczyt {{ font-size: 32px; font-weight: bold; color: #27ae60; background: #e8f8f5; padding: 10px; border-radius: 10px; margin: 20px 0; letter-spacing: 2px; }}
        .uwaga {{ font-size: 13px; color: #b9770e; background: #fef5e7; padding: 8px; border-radius: 8px; margin-bottom: 15px; }}
        img {{ max-width: 100%; height: auto; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }}
        .chart-container {{ position: relative; margin-top: 10px; height: 220px; width: 100%; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Bieżący Stan Licznika</h1>
        <div class="status">Ostatnia aktualizacja danych:<br><span class="timestamp">{timestamp}</span></div>
        <div class="odczyt">{value} m³</div>
        {uwaga_html}

        <h3>Aktualne zdjęcie z gazomierza:</h3>
        <img src="{img_src}" alt="Zdjęcie licznika">

        <h3>Skumulowany stan licznika (m³):</h3>
        <div class="chart-container">
            <canvas id="gasStateChart"></canvas>
        </div>

        <h3>Chwilowe zużycie gazu pomiędzy odczytami (Δ m³):</h3>
        <div class="chart-container">
            <canvas id="gasDiffChart"></canvas>
        </div>
    </div>

    <script>
        // WYKRES 1: Stan skumulowany licznika
        const ctxState = document.getElementById('gasStateChart').getContext('2d');
        new Chart(ctxState, {{
            type: 'line',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: 'Stan licznika (m³)',
                    data: {json.dumps(values)},
                    borderColor: '#27ae60',
                    backgroundColor: 'rgba(39, 174, 96, 0.05)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: true,
                    pointBackgroundColor: '#27ae60'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ beginAtZero: false }} }}
            }}
        }});

        // WYKRES 2: Zużycie chwilowe (wykres liniowy)
        const ctxDiff = document.getElementById('gasDiffChart').getContext('2d');
        new Chart(ctxDiff, {{
            type: 'line',
            data: {{
                labels: {json.dumps(diff_labels)},
                datasets: [{{
                    label: 'Przyrost (m³)',
                    data: {json.dumps(diff_values)},
                    borderColor: '#e67e22',
                    backgroundColor: 'rgba(230, 126, 34, 0.05)',
                    borderWidth: 2,
                    tension: 0.1,
                    fill: true,
                    pointBackgroundColor: '#e67e22'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            callback: function(value) {{ return value + ' m³'; }}
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def get_last_known_value(file_path="odczyty24h.txt"):
    """Pobiera ostatnią poprawną wartość z historii w razie awarii API"""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                if " | " in last_line:
                    return last_line.split(" | ")[1]
    return "---"


def main():
    image_path = get_latest_image()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not image_path:
        print("Nie znaleziono żadnych zdjęć w folderze img_tmp.")
        last_val = get_last_known_value()
        update_html(now_str, last_val, "img_tmp/alg.jpg", success=False)
        return

    print(f"Przetwarzanie i optymalizacja pliku: {image_path}")

    try:
        image_bytes = optimize_image(image_path)
    except Exception as e:
        print(f"Błąd optymalizacji obrazu: {e}")
        last_val = get_last_known_value()
        update_html(now_str, last_val, image_path, success=False)
        return

    client = genai.Client()

    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    ),
                    (
                        "Na zdjęciu jest licznik gazu z bębenkami cyfrowymi. "
                        "Odczyt składa się zawsze z dokładnie 6 cyfr: 3 cyfry części całkowitej "
                        "i 3 cyfry po przecinku (czerwone). Zachowaj zera wiodące. "
                        "Zwróć TYLKO te 6 cyfr, bez kropki, spacji, jednostek ani innego tekstu."
                    )
                ]
            )
            break
        except Exception as e:
            print(f"Próba {attempt + 1} nieudana: {e}")
            if attempt < 2:
                time.sleep(5)

    counter_value = normalize_reading(response.text) if response and response.text else None

    if counter_value:
        print(f"Ostateczny stan licznika: {counter_value}")
        clean_and_update_history(counter_value)
        update_html(now_str, counter_value, image_path, success=True)
        print("Pliki odczyty24h.txt oraz index.html zostały pomyślnie zaktualizowane.")
    else:
        raw = response.text if response else None
        print(f"Nieprawidłowy lub brak odczytu (odpowiedź modelu: {raw!r}). Przywracanie starej wartości.")
        last_val = get_last_known_value()
        update_html(now_str, last_val, image_path, success=False)


if __name__ == "__main__":
    main()
