"""Pixel-measured layout shared by motion graphics and ASS captions."""


def wrap_text(text, measure, width):
    rows = []
    for paragraph in str(text).split('\n'):
        row = ''
        for word in paragraph.split():
            trial = (row + ' ' + word).strip()
            if row and measure(trial) > width:
                rows.append(row)
                row = ''
            # Long names/URLs may exceed the whole row: split for display only.
            for char in word:
                trial = row + char
                if row and measure(trial) > width:
                    rows.append(row)
                    row = ''
                row += char
            if measure((row + ' ').rstrip()) <= width:
                row += ' '
        if row.strip():
            rows.append(row.strip())
    return [row.rstrip() for row in rows] or ['']


def fit_text(text, measure, width, lines, start, smallest=18):
    low, high, best = smallest, int(start), None
    while low <= high:
        size=(low+high)//2
        rows = wrap_text(text, lambda s: measure(s, size), width)
        if len(rows) <= lines and all(measure(row, size) <= width for row in rows):
            best=(size,rows);low=size+1
        else:
            high=size-1
    if best:return best
    # Never silently discard text. Callers must report an unrenderable layout.
    raise ValueError('Yazı güvenli alana sığmıyor. Daha geniş bir yazı düzeni seçin.')
