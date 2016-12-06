
import os

import logging

logger = logging.getLogger(__name__)

# This function returns a path to the primary image of this emote.
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

# This function will convert the colors of pure alpha pixels to black.
# The pixel will still be 100% transparent, but the color values the pixels
# will have will be zero (black).
def _convert_purealpha_to_black_alpha(img):
    pixdata = img.load()
    for y in xrange(img.size[1]):
        for x in xrange(img.size[0]):
            if pixdata[x, y][3] == 0:
                pixdata[x, y] = (0, 0, 0, 0)
    return img

def _extract_single_image(emote, spritemap_img, position_key, width_key, height_key, autocrop):
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
    
    # Some widths/heights overshoot the spritemap.
    # We correct it here.
    # We will always assume spritemap wrapping is wrong.
    # If the dimensions are too big and cause wrapping, we cut off the emote.
    # If the dimensions are too small after we cut off the emote here, we assume
    # the user accidentally depended on spritemap wrapping.
    weird_wrapping = False
    wrap_cropped = False
    if (width + x) > spritemap_width:
        width_new = width + (spritemap_width - (width + x))
        if width_new < 5:
            weird_wrapping = True
            x = (x + width_new) % spritemap_width
        else:
            wrap_cropped = True
            width = width_new
    if (height + y) > spritemap_height:
        height_new = height + (spritemap_height - (height + y))
        if height_new < 5:
            weird_wrapping = True
            y = (y + height_new) % spritemap_height
        else:
            wrap_cropped = True
            height = height_new
    if weird_wrapping:
        logger.warn("Emote: " + canonical_name(emote) + " might depend on spritemap wrapping. Assuming human error instead. Output possible incorrect.")
    if wrap_cropped:
        logger.warn("Emote: " + canonical_name(emote) + " has been cropped to prevent spritemap wrapping. Output possible incorrect if emote depended on wrapping.")
    
    cut_out = spritemap_img.crop((x, y, x + width, y + height))
    if (autocrop):
        # Auto crop removes unnecessary transparency surrounding our image.
        if cut_out.mode != "RGBA":
            cut_out = cut_out.convert("RGBA")
        
        # The getbox() function expects a black border.
        # It will return a dimension with as much black border gone as possible.
        imageBox = _convert_purealpha_to_black_alpha(cut_out.copy()).getbbox()
        if imageBox is not None:
            cut_out = cut_out.crop(imageBox)
            (width, height) = cut_out.size
            x += imageBox[0]
            y += imageBox[1]
        else:
            logger.warn('Emote: '+canonical_name(emote)+' is empty')
    
    # We explicitly set the width and height values in the emote if it was missing.
    # This will make our output more consistent and makes it easier to process.
    emote[width_key] = int(width)
    emote[height_key] = int(height)
    
    if (x > 0 or y > 0):
        # We explicitly set the (hover-)background-position on the spritemap here.
        # This will make our output more consistent and makes it easier to process.
        # The values will be normalized to px.
        emote[position_key] = ['-'+str(x)+'px', '-'+str(y)+'px']
    elif position_key in emote:
        # But we remove the position key if it yields no benefits.
        # This might save a few bytes.
        del emote[position_key]
    
    return cut_out

def extract_single_image(emote, spritemap_img, autocrop=True):
    return _extract_single_image(emote, spritemap_img, 'background-position', 'width', 'height', autocrop)

def has_hover(emote):
    
    if "has_hover" in emote:
        return emote['has_hover']

    has_hover = 'hover-background-position' in emote or 'hover-background-image' in emote
    emote['has_hover'] = has_hover

    weird_hover = False
    if not has_hover and 'hover-height' in emote:
        weird_hover = True
        del emote['hover-height']

    if not has_hover and 'hover-width' in emote:
        weird_hover = True
        del emote['hover-width']

    if weird_hover:
        logger.warn("Emote: " + canonical_name(emote) + " has hover dimension(s) but no hover-background-position or hover-background-image. Assuming this is NOT a hover emote.")

    return has_hover

def extract_single_hover_image(emote, spritemap_img, autocrop=False):
    return _extract_single_image(emote, spritemap_img, 'hover-background-position', 'hover-width', 'hover-height', autocrop)

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
