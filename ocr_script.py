import os
import glob
import io
import time
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

def clean_and_update_history(new_value, file_path="odczyty24h.txt"):
    """Zapisuje nowy odczyt i usuwa wpisy starsze niż 24 godziny"""
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    updated_lines = []

    # 1. Odczytaj i przefiltruj istniejącą historię
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    date_part = line.split(" | ")[0]
                    entry_time = datetime.strptime(date_part, "%Y-%m-%d %H:%M:%S")
                    if entry_time >= cutoff_time:
                        updated_lines.append(line)
                except (ValueError, IndexError):
                    continue

    # 2. Dodaj nowy odczyt
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    new_entry = f"{timestamp} | {new_value}"
    updated_lines.append(new_entry)

    # 3. Zapisz zaktualizowaną historię
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

def main():
    image_path = get_latest_image()
    if not image_path:
        print("Nie znaleziono żadnych zdjęć w folderze img_tmp.")
        return

    print(f"Przetwarzanie i optymalizacja pliku: {image_path}")
    
    try:
        image_bytes = optimize_image(image_path)
        print(f"Rozmiar pliku po optymalizacji: {len(image_bytes) / 1024:.2f} KB")
    except Exception as e:
        print(f"Błąd optymalizacji obrazu: {e}")
        return

    # Inicjalizacja klienta Gemini
    client = genai.Client()

    # Wysyłanie zapytania z potrójną próbą w razie tymczasowych błędów sieciowych
    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    ),
                    (
                        "Na zdjęciu znajduje się licznik gazu. "
                        "1. Zlokalizuj czarną lub białą tabliczkę z bębenkami cyfrowymi (cyfry główne oraz czerwone cyfry po przecinku). "
                        "2. Odczytaj cały stan licznika. Jeśli na liczniku są zera wiodące (np. 00123), zachowaj je. "
                        "3. Jeśli licznik posiada miejsca po przecinku (zazwyczaj 3 cyfry w czerwonej ramce), oddziel je kropką (np. 123.456). "
                        "4. Zwróć TYLKO I WYŁĄCZNIE samą liczbę. Nie dopisuj słów m3, 'stan', spacji ani znaków nowej linii."
                    )
                ]
            )
            break
        except Exception as e:
            print(f"Próba {attempt + 1} nieudana: {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                raise e

    if response and response.text:
        # Czyszczenie wyniku ze zbędnych spacji i kropek na końcu, jeśli model je dopisał
        counter_value = response.text.strip().replace(" ", "").rstrip(".")
        
        print(f"Odczytany stan licznika: {counter_value}")
        clean_and_update_history(counter_value)
        print("Plik odczyty24h.txt został zaktualizowany.")
    else:
        print("Nie udało się uzyskać odpowiedzi od modelu Gemini.")

if __name__ == "__main__":
    main()
