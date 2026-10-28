import cv2, numpy as np, sys
IMG = sys.argv[1] if len(sys.argv) > 1 else "alg.jpg"
X0, X1, Y0, Y1 = 264, 404, 222, 262   # pasek z cyframi
SLANT = 0.10                          # prostowanie kursywy
THR = 0.25                            # próg zapalenia segmentu
DW = 26                               # typowa szerokość jednej cyfry (px)
SEG = {"a": (0.15, 0.85, 0.00, 0.22), "b": (0.60, 1.00, 0.08, 0.48),
       "c": (0.60, 1.00, 0.52, 0.92), "d": (0.15, 0.85, 0.78, 1.00),
       "e": (0.00, 0.40, 0.52, 0.92), "f": (0.00, 0.40, 0.08, 0.48),
       "g": (0.15, 0.85, 0.38, 0.62)}
DIGITS = {"abcdef": 0, "bc": 1, "abdeg": 2, "abcdg": 3, "bcfg": 4,
          "acdfg": 5, "acdefg": 6, "abc": 7, "abcdefg": 8, "abcdfg": 9}

img = cv2.imread(IMG, cv2.IMREAD_GRAYSCALE)
strip = img[Y0:Y1, X0:X1]; h, w = strip.shape
M = np.float32([[1, -SLANT, SLANT * h], [0, 1, 0]])
strip = cv2.warpAffine(strip, M, (w, h), flags=cv2.WARP_INVERSE_MAP,
                       borderMode=cv2.BORDER_REPLICATE)
strip = cv2.GaussianBlur(strip, (3, 3), 0)
bw = cv2.adaptiveThreshold(strip, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                           cv2.THRESH_BINARY_INV, 15, 6)

# usuń drobny szum
n, lab, st, _ = cv2.connectedComponentsWithStats(bw)
for k in range(1, n):
    if st[k, cv2.CC_STAT_AREA] < 8:
        bw[lab == k] = 0

# granice cyfr z rzutu kolumn
ink = (bw > 0).sum(axis=0) >= 2
runs, s = [], None
for x, v in enumerate(ink):
    if v and s is None: s = x
    if not v and s is not None: runs.append([s, x]); s = None
if s is not None: runs.append([s, w])
merged = []
for r in runs:
    if merged and r[0] - merged[-1][1] < 3: merged[-1][1] = r[1]
    else: merged.append(r)
merged = [r for r in merged if r[1] - r[0] >= 4]

# rozetnij sklejone cyfry
cells = []
for xa, xb in merged:
    k = max(1, round((xb - xa) / DW))
    for j in range(k):
        cells.append((xa + (xb - xa) * j // k, xa + (xb - xa) * (j + 1) // k))

dbg = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
res = ""
for xa, xb in cells:
    cell = bw[:, xa:xb]
    rows = np.where((cell > 0).sum(axis=1) >= 1)[0]
    if len(rows) == 0:
        res += "?"; continue
    ya, yb = rows.min(), rows.max() + 1
    cell = cell[ya:yb]; ch, cwi = cell.shape
    if cwi < 0.35 * ch:          # wąska cyfra = jedynka
        res += "1"; continue
    on = ""
    for name, (a, b, c, d) in SEG.items():
        x0, x1 = int(a * cwi), max(int(b * cwi), int(a * cwi) + 1)
        y0, y1 = int(c * ch), int(d * ch)
        lit = cell[y0:y1, x0:x1].mean() / 255 > THR
        if lit: on += name
        cv2.rectangle(dbg, (xa + x0, ya + y0), (xa + x1, ya + y1),
                      (0, 255, 0) if lit else (0, 0, 255), 1)
    res += str(DIGITS.get("".join(sorted(on)), "?"))

cv2.imwrite("diag.png", cv2.resize(dbg, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST))
print(res)
