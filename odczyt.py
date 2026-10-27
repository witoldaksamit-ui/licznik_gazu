import glob, datetime, re, sys, io
from google import genai
from google.genai import types
from PIL import Image

plik = sorted(glob.glob("img_tmp/*"))[-1]

# przycięcie do wyświetlacza (left, top, right, bottom) - dopasuj do swoich zdjęć
img = Image.open(plik).convert("RGB").crop((110, 190, 500, 350))
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=95)

client = genai.Client()  # klucz z GEMINI_API_KEY
r = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
        "To wyświetlacz LCD licznika gazu. Odczytaj wszystkie cyfry stanu licznika "
        "(ramka wokół ostatnich cyfr to część dziesiętna, ignoruj odblaski). "
        "Odpowiedz wyłącznie liczbą bez spacji, np. 98245. "
        "Jeśli odczyt jest niepewny, odpowiedz: BRAK.",
    ],
)
tekst = (r.text or "").strip()

if not re.fullmatch(r"\d{5,8}", tekst):
    print(f"Nieudany odczyt: {tekst!r}")
    sys.exit(0)

wartosc = int(tekst)

# walidacja względem poprzedniego odczytu
try:
    ostatni = open("odczyty.txt").read().strip().splitlines()[-1]
    poprzednia = int(ostatni.split(";")[-1])
    if wartosc < poprzednia or wartosc - poprzednia > 5000:
        print(f"Odrzucono podejrzany odczyt: {wartosc} (poprzedni {poprzednia})")
        sys.exit(0)
except (FileNotFoundError, IndexError, ValueError):
    pass

with open("odczyty.txt", "a") as f:
    f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M};{plik};{wartosc}\n")
