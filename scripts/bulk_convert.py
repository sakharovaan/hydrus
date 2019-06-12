import os, glob
from multiprocessing import Pool


def convert_pillow(paths):
    import PIL.Image, PIL.ImageFile
    import os, stat

    for file in paths:
        try:
            print(file)
            PIL.Image.open(file).save(file[:-3] + 'png', optimize=True)
        except Exception as e:
            print(e)
        else:
            os.chmod(file, stat.S_IWRITE)
            os.unlink(file)

def convert_magick(paths):
    from wand.image import Image

    for file in paths:
        try:
            print(file)
            with Image(filename=file) as img:
                img.format = 'png'
                img.save(filename=file[:-3] + 'png')

        except Exception as e:
            print(e)
        else:
            os.unlink(file)


if __name__ == '__main__':
    # 5.34
    files = glob.iglob('G:\\import\\HCG Pack\\**\\*', recursive=True)
    chunks = []
    for file in files:
        if len(os.path.splitext(file)) > 1 and os.path.splitext(file)[1].lower() == '.bmp':
            if len(chunks) == 0:
                chunks.append([file])
            elif len(chunks) < 5 and len(chunks[-1]) == 50:
                chunks.append([file])
            elif len(chunks) <= 5 and len(chunks[-1]) < 50:
                chunks[-1].append(file)
            elif len(chunks) == 5 and len(chunks[-1]) == 50:
                chunks[-1].append(file)

                with Pool(5) as p:
                    lines = p.map(convert_pillow, chunks)

                for line in lines:
                    print(line)
                chunks = []
    with Pool(5) as p:
        lines = p.map(convert_pillow, chunks)