"""The learning-session companion: a small pixel watchdog drawn from code, with moods.

No image files: shapes are rasterised onto a 32x32 grid once per mood and painted as
rectangles on a Tk canvas.
"""
import functools

COLORS = {'O': '#3b2a20', 'F': '#e8b872', 'E': '#a8672e', 'W': '#fbefd9', 'N': '#2b2118', 'K': '#2b2118',
          'P': '#f08a9b', 'M': '#7a2e2e', 'T': '#5ab0e8', 'S': '#ffcf33', 'C': '#f3a583', 'H': '#ffffff', 'R': '#e5484d'}
SIZE = 32
MOODS = ('wach', 'zufrieden', 'stolz', 'genervt', 'traurig')
SAYINGS = {'wach': 'Ich passe mit auf.', 'zufrieden': 'Läuft gut.', 'stolz': 'Stark, du bleibst dran.',
           'genervt': 'Hm. Das war nicht der Plan.', 'traurig': 'Komm zurück, ich warte hier.'}
SUMMARY_SAYINGS = {'stolz': 'Kein einziges Mal abgedriftet. Stark.', 'zufrieden': 'Gut gemacht, du bist meistens drangeblieben.',
                   'traurig': 'Heute war es zäh. Nächstes Mal schaffen wir mehr.'}


def mood_for(focus_streak, drift_streak):
    if drift_streak >= 2:
        return 'traurig'
    if drift_streak == 1:
        return 'genervt'
    if focus_streak >= 3:
        return 'stolz'
    if focus_streak >= 1:
        return 'zufrieden'
    return 'wach'


def summary_mood(checks, drifts):
    if not drifts:
        return 'stolz' if checks else 'zufrieden'
    return 'zufrieden' if drifts * 3 <= checks else 'traurig'


def ellipse(cx, cy, rx, ry):
    return {(x, y) for y in range(SIZE) for x in range(SIZE) if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1}


def line(x0, y0, x1, y1, thick=1):
    steps = max(abs(x1 - x0), abs(y1 - y0)) or 1
    points = {(round(x0 + (x1 - x0) * i / steps), round(y0 + (y1 - y0) * i / steps)) for i in range(steps + 1)}
    return {(x, y + t) for x, y in points for t in range(thick)}


def box(x0, y0, x1, y1):
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def mirror(points):
    return {(SIZE - 1 - x, y) for x, y in points}


def both(points):
    return points | mirror(points)


def picture(rows, x, y):
    """Pixels from a tiny picture; each letter is a colour key."""
    return {(x + i, y + j): c for j, row in enumerate(rows) for i, c in enumerate(row) if c != '.'}


class Face:
    def __init__(self):
        self.cells = {}

    def fill(self, points, color):
        for p in points:
            if 0 <= p[0] < SIZE and 0 <= p[1] < SIZE:
                self.cells[p] = color

    def blob(self, points, color):
        """A filled shape with a dark outline along its own edge."""
        self.fill(points, color)
        self.fill({(x, y) for x, y in points if not {(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)} <= points}, 'O')

    def put(self, mapping):
        for p, color in mapping.items():
            self.fill({p}, color)


SPARKLE = ('..S..', '..S..', 'SSSSS', '..S..', '..S..')
SMALL_SPARKLE = ('.S.', 'SSS', '.S.')
ANGER = ('.R.R.', 'RR.RR', '.....', 'RR.RR', '.R.R.')
TEAR = ('.T.', '.T.', 'TTT', 'TTT', 'TTT', '.T.')


@functools.lru_cache(maxsize=None)
def grid(mood):
    f = Face()
    sad = mood == 'traurig'
    # Floppy ears first, the head on top; sad ears hang lower and longer.
    f.blob(both(ellipse(5.5, 16.5, 3.6, 8.2) if sad else ellipse(5.8, 12.5, 3.9, 7.4)), 'E')
    head = ellipse(15.5, 15.2, 10.3, 10.6)
    f.blob(head, 'F')
    inside = {p for p in head if f.cells[p] != 'O'}
    f.fill(ellipse(15.5, 9.5, 1.3, 4.6) & inside, 'W')         # blaze between the eyes
    f.fill(ellipse(15.5, 20.6, 6.4, 4.7) & inside, 'W')        # muzzle
    f.fill(ellipse(15.5, 18.2, 2.2, 1.4), 'N')                 # nose
    f.fill({(15, 20), (16, 20)}, 'O')

    if mood == 'wach':
        f.fill(both(ellipse(10.5, 13.4, 1.7, 2.3)), 'K')
        f.fill({(10, 12), (20, 12)}, 'H')
        f.fill(both(line(12, 22, 13, 23)) | line(14, 23, 17, 23), 'O')            # small calm smile
    elif mood in ('zufrieden', 'stolz'):
        f.fill(both(line(8, 14, 10, 12, 2) | line(10, 12, 13, 14, 2)), 'K')        # smiling eyes
        f.fill(both(box(6, 17, 8, 18)), 'C')                                       # cheeks
        mouth = box(11, 22, 20, 26) & ellipse(15.5, 21.6, 4.8, 4.9)
        f.blob(mouth, 'M')
        f.fill(line(11, 22, 20, 22), 'O')
        f.fill({p for p in ellipse(15.5, 25.2, 2.4, 1.6) & mouth if f.cells[p] != 'O'}, 'P')  # tongue
        if mood == 'stolz':
            f.put(picture(SPARKLE, 26, 1))
            f.put(picture(SPARKLE, 0, 25))
            f.put(picture(SMALL_SPARKLE, 1, 2))
            f.put(picture(SMALL_SPARKLE, 28, 26))
    elif mood == 'genervt':
        f.fill(both(line(7, 8, 13, 11, 2)), 'O')                                    # heavy brows pulled down to the middle
        f.fill(both(line(8, 13, 13, 13)), 'O')                                      # half-closed lids
        f.fill(both(box(9, 14, 12, 15)), 'H')                                       # narrow eyes ...
        f.fill(box(11, 14, 12, 15) | box(21, 14, 22, 15), 'K')                      # ... looking away to the side
        f.fill(both(line(9, 16, 12, 16)), 'O')
        f.fill(line(12, 23, 19, 23) | both({(11, 24), (10, 25)}), 'O')              # flat mouth, corners down
        f.put(picture(ANGER, 26, 2))
    elif sad:
        f.fill(both(line(7, 11, 13, 8, 2)), 'O')                                    # brows raised in the middle
        f.fill(both(ellipse(10.5, 14.2, 1.9, 2.2)), 'K')
        f.fill(both({(10, 13), (11, 13), (10, 14)}), 'H')                           # watery eyes
        f.fill(line(13, 23, 18, 23) | both({(12, 24), (11, 25)}), 'O')              # downturned mouth
        f.put(picture(TEAR, 9, 17))
    else:
        raise KeyError(mood)
    return tuple(''.join(f.cells.get((x, y), '.') for x in range(SIZE)) for y in range(SIZE))


def draw(canvas, mood, scale, background):
    """Paint the companion on a canvas of SIZE*scale pixels."""
    canvas.delete('all')
    canvas.configure(bg=background)
    for y, row in enumerate(grid(mood)):
        x = 0
        while x < SIZE:
            cell, start = row[x], x
            while x < SIZE and row[x] == cell:
                x += 1
            if cell != '.':
                canvas.create_rectangle(start * scale, y * scale, x * scale, (y + 1) * scale,
                                        fill=COLORS[cell], outline=COLORS[cell])
