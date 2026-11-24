# Figures — technical rules

The caption paragraph style, Word fields and output verification are build-side rules, so they are in `build-technical.md`.

## Composite transparent backgrounds onto white

Most manuscript figures are **RGBA (transparent background) TIFF/PNG** files. Converting one directly with `.convert('RGB')` fills the transparent area with **black**, which turns a figure completely black or gives several figures a black background.

```python
im = Image.open(src)
if im.mode in ('RGBA','LA') or (im.mode=='P' and 'transparency' in im.info):
    im = im.convert('RGBA')
    bg = Image.new('RGB', im.size, (255,255,255))
    bg.paste(im, mask=im.split()[-1])          # composite onto white
    im = bg
else:
    im = im.convert('RGB')
```

After adding or changing a figure, **self-check with the mean of the corner pixels and the number of unique colors.**
A corner mean below 60 means a black background, and 2 or fewer unique colors means a broken file.

## What figures must not carry

- Screenshots of software UI (EDS quantification dialogs, measurement program windows)
- Auto-generated title text (`EBSD Layered Image 10` and similar)
- Slide decoration (colored header bands, logos, page numbers)

**This list targets what gets in the way of reading the figure.** Labels that an analysis or calculation program prints automatically on its output stay as they are when they do not get in the way.

If the figure must show numbers, **redraw them as a proper table** with the same values. When a figure becomes a table, the wording in the text and caption must change with it (`spectrum` → `quantification result`).
