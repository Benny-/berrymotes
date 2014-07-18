
import os

# This function returns a path to a single image.
# This image can be the same as sprite-map image.
def get_single_image_path(emote, extension=None):
    if extension:
        emote['single_image_extension'] = extension.lower()

    if 'single_image_extension' in emote:
        extension = emote['single_image_extension']
    else:
        extension = 'png'

    return os.path.join( *(['output']+((emote['canonical']+"."+extension).split('/'))))

# Please note: A emote's hover image is optional.
# There is no guarantee this image exists.
def get_single_hover_image_path(emote, extension=None):
    if extension:
        emote['single_hover_image_extension'] = extension.lower()

    if 'single_hover_image_extension' in emote:
        extension = emote['single_hover_image_extension']
    else:
        extension = 'png'

    return os.path.join( *(['output']+((emote['canonical']+"_hover."+extension).split('/'))))

def _extract_single_image(emote, spritemap_img, position_key, width_key, height_key):
    spritemap_width = spritemap_img.size[0]
    spritemap_height = spritemap_img.size[1]

    x=0
    y=0
    width = spritemap_width
    height = spritemap_height

    if 'width' in emote:
        width = emote['width']
    if 'height' in emote:
        height = emote['height']

    if width_key in emote:
        width = emote[width_key]
    if height_key in emote:
        height = emote[height_key]

    if position_key in emote:
        if len(emote[position_key]) > 0:
            raw_x = emote[position_key][0]
            x = int(raw_x.strip('-').strip('px').strip('%'))
            if '-' not in raw_x and '%' not in raw_x:
                x = spritemap_width - x
            # TODO: Potential unhandled edge case with positive percentage.
            if raw_x.endswith('%'):
                x = width * x / 100

        if len(emote[position_key]) > 1:
            raw_y = emote[position_key][1]
            y = int(raw_y.strip('-').strip('px').strip('%'))
            if '-' not in raw_y and '%' not in raw_y:
                y = spritemap_height - y
            # TODO: Potential unhandled edge case with positive percentage.
            if raw_y.endswith('%'):
                y = height * y / 100

    x = x % spritemap_width
    y = y % spritemap_height
    return spritemap_img.crop((x, y, x + width, y + height))

def extract_single_image(emote, spritemap_img):
    return _extract_single_image(emote, spritemap_img, 'background-position', 'width', 'height')

def has_hover(emote):
    return 'hover-background-position' in emote or 'hover-background-image' in emote

def extract_single_hover_image(emote, spritemap_img):
    return _extract_single_image(emote, spritemap_img, 'hover-background-position', 'hover-width', 'hover-height')

def friendly_name(emote):
    '''
    This function is API locked, it is used to get a unique emote name in a subreddit
    This name is not globally unique
    '''
    return emote['canonical'].split("/").pop()

def canonical_name(emote):
    '''
    This name is globally unique
    '''
    return emote['canonical']

def get_explode_directory(emote):
    return os.path.join(os.path.dirname(get_single_image_path(emote)), friendly_name(emote)+"_exploded")
