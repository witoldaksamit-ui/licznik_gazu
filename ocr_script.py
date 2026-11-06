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

MAX_JUMP_M3 = 50.0  # maksymalny sensowny przyrost między odczytami (dostosuj do swojego interwału)


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


def get_last_known_value(file_path="odczyty24h.txt"):
    """Pobiera ostatnią poprawną wartość z historii w razie awarii API"""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]
            if lines:
                last_line = lines[-1].strip()
                if " | " in last_line:
                    return last_line.split(" | ")[1]
    return "---"


def is_plausible(new_value, file_path="odczyty24h.txt"):
    """Sprawdza, czy odczyt nie jest mniejszy od poprzedniego i nie skacze nierealistycznie."""
    last = get_last_known_value(file_path)
    try:
        last_f = float(last)
    except ValueError:
        return True  # brak historii, nie ma z czym porównać
    diff = float(new_value) - last_f
    return 0 <= diff <= MAX_JUMP_M3


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


def update_html(timestamp, value, image_path, success=True, file_path="index.html", template_path="index_template.html"):
    """Generuje index.html z szablonu index_template.html (gaz + temperatura)"""
    cache_buster = int(time.time())
    img_src = f"{image_path}?t={cache_buster}"

    uwaga_html = ""
    if not success:
        uwaga_html = '<div class="uwaga">Ostatni odczyt się nie powiódł, wyświetlana jest poprzednia poprawna wartość.</div>'

    labels, values, diff_labels, diff_values = get_history_data()

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    replacements = {
        "__TIMESTAMP__": timestamp,
        "__VALUE__": str(value),
        "__UWAGA__": uwaga_html,
        "__IMG_SRC__": img_src,
        "__STATE_LABELS__": json.dumps(labels),
        "__STATE_VALUES__": json.dumps(values),
        "__DIFF_LABELS__": json.dumps(diff_labels),
        "__DIFF_VALUES__": json.dumps(diff_values),
    }
    for key, val in replacements.items():
        html = html.replace(key, val)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)


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

    prompt = (
        "Na zdjęciu jest wyświetlacz LCD licznika gazu. "
        "Odczyt składa się z dokładnie 6 cyfr czytanych od lewej do prawej: "
        "3 cyfry części całkowitej i 3 cyfry po przecinku. "
        "Część po przecinku jest otoczona prostokątną ramką, ale pionowa linia ramki "
        "NIE jest cyfrą ani kropką. Cyfry mogą być rozdzielone odstępem, który "
        "też NIE jest cyfrą. Policz wszystkie widoczne cyfry i niczego nie dopisuj "
        "ani nie pomijaj, w szczególności nie dodawaj zer na początku. "
        "Zwróć TYLKO te 6 cyfr, bez kropki, spacji, jednostek ani innego tekstu."
    )

    counter_value = None
    raw = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt,
                ]
            )
            raw = response.text
            candidate = normalize_reading(raw)
            if candidate and is_plausible(candidate):
                counter_value = candidate
                break
            print(f"Próba {attempt + 1}: odrzucony odczyt {raw!r}")
        except Exception as e:
            print(f"Próba {attempt + 1} nieudana: {e}")
        if attempt < 2:
            time.sleep(5)

    if counter_value:
        print(f"Ostateczny stan licznika: {counter_value}")
        clean_and_update_history(counter_value)
        update_html(now_str, counter_value, image_path, success=True)
        print("Pliki odczyty24h.txt oraz index.html zostały pomyślnie zaktualizowane.")
    else:
        print(f"Brak wiarygodnego odczytu (ostatnia odpowiedź modelu: {raw!r}). Przywracanie starej wartości.")
        last_val = get_last_known_value()
        update_html(now_str, last_val, image_path, success=False)


if __name__ == "__main__":
    main()
