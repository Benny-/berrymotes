
import os
import collections

class Emote(collections.MutableMapping):

    def __init__(self, emote_data):
        self.emote_data = emote_data
        self.single_image_format = 'png'
        self.single_hover_image_format = 'png'

    # This function returns a path to a single image.
    # This image can be the same as sprite-map image.
    def get_single_image_path(self, extension=None):
        if extension:
            self.single_image_format = extension.lower()
        return os.path.join( *(['single_emotes']+((self.emote_data['canonical']+"."+self.single_image_format).split('/'))))

    # Please note: A emote's hover image is optional.
    # There is no guarantee this image exists.
    def get_single_hover_image_path(self, extension=None):
        if extension:
            self.single_hover_image_format = extension.lower()
        return os.path.join( *(['single_emotes']+((self.emote_data['canonical']+"_hover."+self.single_hover_image_format).split('/'))))

    def _extract_single_image(self, spritemap_img, position_key, width_key, height_key):
        spritemap_width = spritemap_img.size[0]
        spritemap_height = spritemap_img.size[1]

        x=0
        y=0
        width = self.emote_data[width_key]
        height = self.emote_data[height_key]

        if position_key in self.emote_data:
            if len(self.emote_data[position_key]) > 0:
                x = int(self.emote_data[position_key][0].strip('-').strip('px').strip('%'))
                if self.emote_data[position_key][0].endswith('%'):
                    x = width * x / 100;

            if len(self.emote_data[position_key]) > 1:
                y = int(self.emote_data[position_key][1].strip('-').strip('px').strip('%'))
                if self.emote_data[position_key][1].endswith('%'):
                    y = height * y / 100;

        x = x % spritemap_width
        y = y % spritemap_height
        return spritemap_img.crop((x, y, x + width, y + height))

    def extract_single_image(self, spritemap_img):
        return self._extract_single_image(spritemap_img, 'background-position', 'width', 'height')

    def has_hover(self):
        return 'hover-background-position' in self.emote_data or 'hover-background-image' in self.emote_data

    def extract_single_hover_image(self, spritemap_img):
        return self._extract_single_image(spritemap_img, 'hover-background-position', 'hover-width', 'hover-height')

    def __getitem__(self, key):
        return self.emote_data.get(key)

    def __setitem__(self, key, value):
        self.emote_data[key] = value

    def __delitem__(self, key):
        del self.emote_data[key]

    def __iter__(self):
        return iter(self.emote_data)

    def __len__(self):
        return len(self.emote_data)

    def __str__(self):
        return self.emote_data['canonical']

    def __unicode__(self):
        return u"" + self.emote_data['canonical']
