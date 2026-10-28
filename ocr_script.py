import os
import glob
from datetime import datetime, timedelta
from google import genai
from google.genai import types

def get_latest_image():
    # Szuka plików graficznych w folderze img_tmp
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
    files = []
    for ext in image_extensions:
        files.extend(glob.glob(f"img_tmp/{ext}"))
    
    if not files:
        return None
    # Zwraca najnowszy plik
    return max(files, key=os.path.getmtime)

def clean_and_update_history(new_value, file_path="odczyty24h.txt"):
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    updated_lines = []

    # 1. Odczytaj istniejącą historię i przefiltruj wpisy (starsze niż 24h są usuwane)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    # Format linii: YYYY-MM-DD HH:MM:SS | wartość
                    date_str = line.split(" | ")[0]
                    entry_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    
                    if entry_time >= cutoff_time:
                        updated_lines.append(line)
                except (ValueError, IndexError):
                    # Pomija linie o niepoprawnym formacie, jeśli takie się trafią
                    continue

    # 2. Dodaj nowy odczyt z bieżącą datą i godziną
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    new_entry = f"{timestamp} | {new_value}"
    updated_lines.append(new_entry)

    # 3. Zapisz zaktualizowaną historię z powrotem do pliku
    with open(file_path, "w", encoding="utf-8") as range_file:
        for line in updated_lines:
            range_file.write(line + "\n")

def main():
    image_path = get_latest_image()
    if not image_path:
        print("Nie znaleziono żadnych zdjęć w folderze img_tmp.")
        return

    print(f"Przetwarzanie pliku: {image_path}")

    # Inicjalizacja klienta Gemini
    client = genai.Client()

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # Wysyłamy zdjęcie z precyzyjnym promptem dla licznika
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/jpeg",
            ),
            "Odczytaj wartość licznika ze zdjęcia. Zwróć tylko i wyłącznie samą odczytaną liczbę (cyfry), bez żadnych jednostek, spacji czy dodatkowego tekstu."
        ]
    )

    counter_value = response.text.strip()
    print(f"Odczytany stan licznika: {counter_value}")

    # Aktualizacja pliku z historią 24h
    clean_and_update_history(counter_value)
    print("Plik odczyty24h.txt został zaktualizowany.")

if __name__ == "__main__":
    main()
