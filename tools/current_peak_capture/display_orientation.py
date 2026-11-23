"""Orient the complete matrix for the user's inverted UNO Q mounting."""
OLD = '''  // UNO Q's physical matrix is wired right-to-left relative to the raw pixel
  // buffer. Mirror X so values such as 5.0 do not appear as 0.5.
  g_matrix_pixels[y * MATRIX_W + (MATRIX_W - 1 - x)] = 1;'''
NEW = '''  // Inverted bench mounting: reverse both axes relative to the previous
  // frame. Remove the old X mirror (19 must read 19, not 91) and flip Y.
  // Transform the whole image, including decimal points and status markers.
  g_matrix_pixels[(MATRIX_H - 1 - y) * MATRIX_W + x] = 1;'''


def apply(source):
    if NEW in source:
        return source
    assert source.count(OLD) == 1, 'Unexpected matrix mapping; refuse ambiguous edit'
    return source.replace(OLD, NEW)
