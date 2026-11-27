"""The learning-session companion: a small pixel watchdog drawn from code, with moods.

No image files: a 16x16 grid plus a few mood-specific pixels, painted as rectangles on a Tk canvas.
"""

COLORS = {'O': '#3b2a20', 'F': '#e8b872', 'E': '#a8672e', 'W': '#fbefd9', 'N': '#3b2a20', 'K': '#2b2118',
          'P': '#e8788a', 'T': '#5ab0e8', 'S': '#ffcf33', 'C': '#f0a07c', 'H': '#ffffff'}
SIZE = 16
BASE = ('................',
        '..OOO......OOO..',
        '.OEEEOOOOOOEEEO.',
        '.OEEOFFFFFFOEEO.',
        '.OEEOFFFFFFOEEO.',
        '.OEOFFFFFFFFOEO.',
        '.OEOFFFFFFFFOEO.',
        '.OEOFFFFFFFFOEO.',
        '..OOFFWWWWFFOO..',
        '...OFWWNNWWFO...',
        '...OFWWWWWWFO...',
        '...OFWWWWWWFO...',
        '....OWWWWWWO....',
        '.....OOOOOO.....',
        '................',
        '................')
# Sad ears hang lower and closer to the head.
SAD_BASE = ('................',
            '................',
            '....OOOOOOOO....',
            '..OOOFFFFFFOOO..',
            '.OEEOFFFFFFOEEO.',
            '.OEOFFFFFFFFOEO.',
            '.OEOFFFFFFFFOEO.',
            '.OEOFFFFFFFFOEO.',
            '.OEOFFWWWWFFOEO.',
            '.OOOFWWNNWWFOOO.',
            '...OFWWWWWWFO...',
            '...OFWWWWWWFO...',
            '....OWWWWWWO....',
            '.....OOOOOO.....',
            '................',
            '................')


def pixels(text):
    return [(int(x), int(y), c) for x, y, c in (item.split(',') for item in text.split())]


SMILE = '5,5,K 4,6,K 6,6,K 10,5,K 9,6,K 11,6,K 4,7,C 11,7,C 6,11,O 9,11,O 7,11,P 8,11,P 7,12,P 8,12,P'
MOODS = {
    # attentive: round eyes with a highlight, small mouth
    'wach': pixels('5,5,K 5,6,K 6,5,K 6,6,K 9,5,K 9,6,K 10,5,K 10,6,K 5,5,H 9,5,H 7,11,O 8,11,O'),
    # content: smiling eyes, tongue out
    'zufrieden': pixels(SMILE),
    # proud: content plus sparkles
    'stolz': pixels(SMILE + ' 14,12,S 13,13,S 14,13,S 15,13,S 14,14,S 1,13,S 2,0,S 1,1,S 2,1,S 3,1,S 2,2,S'),
    # annoyed: furrowed brows, half-closed eyes, flat mouth
    'genervt': pixels('4,4,O 5,4,O 6,5,O 11,4,O 10,4,O 9,5,O 5,6,K 6,6,K 9,6,K 10,6,K 6,11,O 7,11,O 8,11,O 9,11,O'),
    # sad: raised inner brows, a tear, downturned mouth
    'traurig': pixels('4,5,O 5,4,O 6,4,O 11,5,O 10,4,O 9,4,O 5,6,K 6,6,K 9,6,K 10,6,K 5,7,T 5,8,T 7,11,O 8,11,O 6,12,O 9,12,O'),
}
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


def grid(mood):
    rows = [list(row) for row in (SAD_BASE if mood == 'traurig' else BASE)]
    for x, y, color in MOODS[mood]:
        rows[y][x] = color
    return rows


def draw(canvas, mood, scale, background):
    """Paint the companion on a canvas of SIZE*scale pixels."""
    canvas.delete('all')
    canvas.configure(bg=background)
    for y, row in enumerate(grid(mood)):
        for x, cell in enumerate(row):
            if cell != '.':
                canvas.create_rectangle(x * scale, y * scale, (x + 1) * scale, (y + 1) * scale,
                                        fill=COLORS[cell], outline=COLORS[cell])
