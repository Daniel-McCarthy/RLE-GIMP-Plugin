#!/usr/bin/env python2

##############
##  Imports ##
##############
import os
import inspect
import sys
from array import array
from gimpfu import *

####################
##   Exceptions   ##
####################


def alert_and_raise(error_message):
    pdb.gimp_message(error_message)
    raise Exception(error_message)


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


#####################
##   Entry Point   ##
#####################


def identify_and_load_format(file_name, uri_path):
    file_extension = os.path.splitext(file_name)
    if ".bmr" not in file_extension and ".rle" not in file_extension:
        error_message = "File not supported. Expected .rle or .bmr, but got: '{0}'.".format(
            file_extension)
        alert_and_raise(error_message)

    file = load_file(file_name)
    # Load raw format if has .bmr extension
    if ".bmr" in file_extension:
        return load_bmr(file)

    # Load encoded RLE format if has expected magic number
    if verify_file_is_rle(file):
        return load_rle(file)

    alert_and_raise(
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


class Color:
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

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
    row_len = 0
    # Read in and convert all colors to 32 bit RGBA
    for _ in range(0, file_size, 2):
        color_bytes = file.read(2)
        color = convert_rgba5551_to_rgba32(color_bytes)
        row.append(color)
        row_len += 1

        # Start new row when we hit the width
        if row_len >= width:
            canvas.append(row)
            row = []
            row_len = 0

    # If a row wasn't finished, add it to the image anyways.
    if row_len > 0:
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
    REPEAT_COLOR_AND_NEWLINE = 0x81

def load_rle(file):
    max_width = 512
    header_length = 12
    has_set_width = False
    file_size = get_file_size(file)
    file.seek(header_length)

    canvas = []
    row = []
    row_len = 0
    # Read in, decode, & convert all colors to 32 bit RGBA
    while file.tell() + 1 < file_size:
        quantity = ord(file.read(1))
        flag = ord(file.read(1))

        if (quantity == 0xFE and flag == 0x81):
            # The seek amount changes for each file and has not yet been determined
            # how to calculate the beginning of the first pixel. For the 0xFE 0x81
            # combination it appears to indicate an interlaced image and has some
            # information before the pixel data begins.
            file.seek(8, os.SEEK_CUR)
            continue

        if flag == EncodedFlags.READ_NUM_COLORS:
            for _ in range(0, quantity):
                color = convert_rgba5551_to_rgba32(file.read(2))
                row.append(color)
                row_len += 1

                if row_len >= max_width:
                    canvas.append(row)
                    row = []
                    row_len = 0

        elif flag == EncodedFlags.REPEAT_COLOR or flag == EncodedFlags.REPEAT_COLOR_AND_NEWLINE:
            color = convert_rgba5551_to_rgba32(file.read(2))
            needs_newline = flag == EncodedFlags.REPEAT_COLOR_AND_NEWLINE 
            wrapped = False

            for _ in range(0, quantity):
                row.append(color)
                row_len += 1
                if row_len >= max_width:
                    wrapped = True
                    canvas.append(row)
                    row = []
                    row_len = 0

            # Wrap if new line flag found ONLY if we haven't already wrapped around image width
            if (needs_newline and not wrapped):
                # Set image width to the position of the new line
                if not has_set_width:
                    has_set_width = True
                    y_pos = len(canvas)
                    if (y_pos > 0):
                        max_width = len(canvas[0])
                    else:
                        max_width = len(row)
                canvas.append(row)
                row = []
                row_len = 0

    # If a row wasn't finished, add it to the image anyways.
    if row_len > 0:
        canvas.append(row)

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

######################
##      Plugin      ##
##   Registration   ##
######################


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

main()
