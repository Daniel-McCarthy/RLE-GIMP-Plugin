#!/usr/bin/env python2

##############
##  Imports ##
##############
import os
import inspect
import sys
from array import array
from gimpfu import *


############
##   IO   ##
############


def get_file_size(file):
    original_pos = file.tell()
    file.seek(0, os.SEEK_END)
    end_pos = file.tell()

    file.seek(0, original_pos)
    return end_pos


def load_file(file_name):
    return open(file_name, "rb")

def read_int_little_endian(file):
    bytes_arr = file.read(4)
    integer = 0
    for i in range(0, len(bytes_arr)):
        integer |= ord(bytes_arr[i]) << (8*i) 
    integer &= 0xFFFFFFFF
    return integer


#####################
##   Entry Point   ##
#####################


def identify_and_load_format(file_name, uri_path):
    file_extension = os.path.splitext(file_name)
    if ".bmr" not in file_extension and ".rle" not in file_extension:
        error_message = "File not supported. Expected .rle or .bmr, but got: '{0}'.".format(
            file_extension)
        pdb.gimp_message(error_message)
        return

    file = load_file(file_name)
    # Load raw format if has .bmr extension
    if ".bmr" in file_extension:
        return load_bmr(file)

    # Load encoded RLE format if has expected magic number
    if verify_file_is_rle(file):
        return load_rle(file)

    pdb.gimp_message(
        "Failed to load image \"{0}\". No _RLE_16_ magic number found, therefore is an invalid RLE image".format(file.name))

########################
##   Color Handling   ##
########################


def convert_rgba5551_to_rgba32(rgba5551_bytes):
    byte1 = ord(rgba5551_bytes[0])
    byte2 = ord(rgba5551_bytes[1])
    rgba5551_short = byte2 << 8 | byte1

    r = rgba5551_short & 0b11111
    g = (rgba5551_short >> 5) & 0b11111
    b = (rgba5551_short >> 10) & 0b11111

    r <<= 3
    g <<= 3
    b <<= 3

    return Color(r, g, b)

def convert_rgb888_to_rgba5551(r, g, b):
    rgba5551_short = 0
    rgba5551_short |= ((r >> 3) & 0b11111)
    rgba5551_short |= ((g >> 3) & 0b11111) << 5
    rgba5551_short |= ((b >> 3) & 0b11111) << 10
    return rgba5551_short


class Color:
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    def __eq__(self, other):
        return isinstance(other, Color) and (self.r == other.r) and (self.g == other.g) and (self.b == other.b)
    
    def __ne__(self, other):
        # Necessary in Python 2 for !=
        return not self.__eq__(other)

def transfer_canvas_to_pixel_region(canvas, pixel_region, width, height):
    region_bytes = array("B", pixel_region[0:width, 0:height])
    byte_index = 0
    
    # Transfer the pixel color bytes to the pixel region data array
    for row_index, row in enumerate(canvas):
        for col_index, pixel_color in enumerate(row):
            region_bytes[byte_index] = pixel_color.r
            region_bytes[byte_index + 1] = pixel_color.g
            region_bytes[byte_index + 2] = pixel_color.b
            byte_index += 3

    # Load in all the pixels to the pixel region at once
    pixel_region[0:width, 0:height] = region_bytes.tostring()


###################################
##   RLE & BMR Format Handling   ##
###################################

def verify_file_is_rle(file):
    magic_number_text = "_RLE_16_"
    first_8_bytes = file.read(8)
    return str(first_8_bytes) in magic_number_text


def load_bmr(file):
    # Note: The width changes on a per game basis. There is no header data
    # to determine the width for the image from. 512px is for Spiderman 1 (PSX).
    width = 512
    file_size = get_file_size(file)

    canvas = []
    row = []
    # Read in and convert all colors to 32 bit RGBA
    for _ in range(0, file_size, 2):
        color_bytes = file.read(2)
        color = convert_rgba5551_to_rgba32(color_bytes)
        row.append(color)

        # Start new row when we hit the width
        if len(row) >= width:
            canvas.append(row)
            row = []

    # If a row wasn't finished, add it to the image anyways.
    if len(row) > 0:
        canvas.append(row)

    # Create Image and Layer to load image onto & copy pixel data in.
    height = len(canvas)
    img = gimp.Image(width, height, RGB)
    lyr = gimp.Layer(img, file.name, width, height,
                     RGB_IMAGE, 100, NORMAL_MODE)
    pixel_region = lyr.get_pixel_rgn(0, 0, width, height)
    transfer_canvas_to_pixel_region(canvas, pixel_region, width, height)

    img.add_layer(lyr, 0)
    img.filename = file.name
    return img


class EncodedFlags:
    READ_NUM_COLORS = 0x00
    REPEAT_COLOR = 0x80

def load_rle(file):
    # Skip header / magic number
    header_length = 8
    file_size = get_file_size(file)
    file.seek(header_length)

    # Determine size of image
    max_width = 512
    decompressed_file_size = read_int_little_endian(file) - header_length
    total_rows = (decompressed_file_size / 2) / max_width

    canvas = []
    row = []
    row_len = 0
    quantity_bits = 0b0111111111111111
    # Read in, decode, & convert all colors to 32 bit RGBA
    while file.tell() + 1 < file_size and len(canvas) < total_rows:
        byte_1 = ord(file.read(1))
        byte_2 = ord(file.read(1))

        quantity = (byte_1 | (byte_2 << 8)) & quantity_bits
        flag = EncodedFlags.REPEAT_COLOR if ((byte_2 & 0x80) > 0) else EncodedFlags.READ_NUM_COLORS

        if flag == EncodedFlags.READ_NUM_COLORS:
            for _ in range(0, quantity):
                color = convert_rgba5551_to_rgba32(file.read(2))
                row.append(color)
                row_len += 1

                if row_len >= max_width:
                    canvas.append(row)
                    row = []
                    row_len = 0

        elif flag == EncodedFlags.REPEAT_COLOR:
            color = convert_rgba5551_to_rgba32(file.read(2))

            for _ in range(0, quantity):
                row.append(color)
                row_len += 1
                if row_len >= max_width:
                    canvas.append(row)
                    row = []
                    row_len = 0

        else:
            pdb.gimp_message("Unsupported flag type found at byte {0}. Flag found: {1}.".format(file.tell(), flag))
            return


    # If a row wasn't finished, add it to the image anyways.
    if row_len > 0:
        canvas.append(row)

    # Rotate pixels on wrong side of image if any are found
    canvas = unshift_columns(canvas)

    # Create Image and Layer to load image onto & copy pixel data in.
    height = len(canvas)
    img = gimp.Image(max_width, height, RGB)
    lyr = gimp.Layer(img, file.name, max_width, height,
                     RGB_IMAGE, 100, NORMAL_MODE)
    pixel_region = lyr.get_pixel_rgn(0, 0, max_width, height)
    transfer_canvas_to_pixel_region(canvas, pixel_region, max_width, height)

    img.add_layer(lyr, 0)
    img.filename = file.name
    return img

def unshift_columns(canvas):
    blue_color = Color(0, 0, 144)
    blue_color2 = Color(0, 0, 208)

    first_row = canvas[0]
    row_len = len(first_row)
    last_pixel = first_row[row_len - 1]
    matches_blue = (last_pixel == blue_color or last_pixel == blue_color2)

    # This blue pixel incidates the column has been encoded
    # If it's not present, no shifting is present.
    if (not matches_blue):
        return canvas

    # Move final two columns to start of the image
    # RLE encodes these columns to the end of the rows
    for i in range(0, len(canvas)):
        current_row = canvas[i]
        current_row.insert(0, current_row.pop(len(current_row) - 1))
        current_row.insert(0, current_row.pop(len(current_row) - 1))
        canvas[i] = current_row

    # Moves each pixel of the first two columns up
    # Pixels are shifted down and top pixels are encoded
    for i in range(0, len(canvas)):
        if (i + 2 < len(canvas)):
            current_row = canvas[i]
            next_row = canvas[i+1]
            current_row[0] = next_row[0]
            current_row[1] = next_row[1]
            canvas[i] = current_row
    return canvas

def save_bmr(editor_image, drawable, filename, raw_filename):
    # Image is duplicated to avoid side effects / flattening user's image
    image = editor_image.duplicate()
    image.flatten()
    width = image.width
    height = image.height

    if (width != 512):
        pdb.gimp_message("Export failed: Image must be width 512. Received width: '{0}'.".format(width))
        return

    layer = image.layers[0]
    pixel_region = layer.get_pixel_rgn(0, 0, width, height)
    region_bytes = array("B", pixel_region[0:width, 0:height])

    converted_color_bytes = bytearray()
    for i in range(0, len(region_bytes), 3):
        r = region_bytes[i]
        g = region_bytes[i+1]
        b = region_bytes[i+2]
        rgba_short = convert_rgb888_to_rgba5551(r, g, b)
        converted_color_bytes.append(rgba_short & 0x00FF)
        converted_color_bytes.append((rgba_short & 0xFF00) >> 8)

    file = open(filename, 'wb')
    file.write(converted_color_bytes)

######################
##      Plugin      ##
##   Registration   ##
######################

def register_save_handlers():
    gimp.register_save_handler('file-neversoft-bmr-save', 'bmr', '')

def register_load_handlers():
    gimp.register_load_handler('file-neversoft-rle-load', 'rle,bmr', '')
    pdb['gimp-register-file-handler-mime'](
        'file-neversoft-rle-load', 'image/rle')


register(
    'file-neversoft-rle-load',
    'load an RLE (.rle) file',
    'load an RLE (.rle) file',
    'Dan McCarthy',
    'Dan McCarthy',
    '2021',
    'Neversoft RLE',
    None,
    [
        (PF_STRING, 'file_name', 'File path for image being opened', None),
        (PF_STRING, 'raw_name', 'URI formatted file path', None),
    ],
    [(PF_IMAGE, 'image', 'Returned image')],
    identify_and_load_format,
    on_query=register_load_handlers,
    menu="<Load>",
)

register(
    'file-neversoft-bmr-save',
    'save an BMR (.bmr) file',
    'save an BMR (.bmr) file',
    'Dan McCarthy',
    'Dan McCarthy',
    '2021',
    'Neversoft BMR',
    '*',
    [
        (PF_IMAGE, "image", "The image to be saved", None),
        (PF_DRAWABLE, "drawable", "The drawable surface of image", None),
        (PF_STRING, "filename", "Name for file being saved", None),
        (PF_STRING, "raw-filename", "Raw name for file being saved", None),
    ],
    [],
    save_bmr,
    on_query = register_save_handlers,
    menu = '<Save>'
)

main()
