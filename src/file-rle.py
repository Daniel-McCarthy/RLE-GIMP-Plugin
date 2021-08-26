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
        pdb.gimp_message(error_message)
        raise(error_message)

    file = load_file(file_name)
    # Load raw format if has .bmr extension
    if ".bmr" in file_extension:
        return load_bmr(file)

    # Load encoded RLE format if has expected magic number
    if verify_file_is_rle(file):
        load_rle(file)

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

    return [r & 0xFF, g & 0xFF, b & 0xFF]


###################################
##   RLE & BMR Format Handling   ##
###################################

def verify_file_is_rle(file):
    magic_number_text = "_RLE_16_"
    first_8_bytes = file.read(8)
    return str(first_8_bytes).__contains__(magic_number_text)


def load_bmr(file):
    width = 512
    file_size = get_file_size(file)

    canvas = []
    line = []
    colors_added = 0
    # Read in and convert all colors to 32 bit RGBA
    for i in range(0, file_size, 2):
        color_bytes = file.read(2)
        color = convert_rgba5551_to_rgba32(color_bytes)
        line.append(color)
        colors_added += 1

        # Break new line when we hit the width
        if colors_added >= width:
            canvas.append(line)
            line = []
            colors_added = 0

    # If a line wasn't finished, add it to the image anyways.
    if colors_added > 0:
        canvas.append(line)

    height = len(canvas)

    # Create Image and Layer to load image onto.
    img = gimp.Image(width, height, RGB)
    lyr = gimp.Layer(img, file.name, width, height,
                     RGB_IMAGE, 100, NORMAL_MODE)

    # Get layer pixel data as a pixel region to draw on
    pixel_region = lyr.get_pixel_rgn(0, 0, width, height)
    pixel_bytes = array("B", pixel_region[0:width, 0:height])

    byte_index = 0
    # Transfer the pixel color bytes to the pixel region data array
    for row_index, row in enumerate(canvas):
        for col_index, pixel_color in enumerate(row):
            pixel_bytes[byte_index] = pixel_color[0]
            pixel_bytes[byte_index + 1] = pixel_color[1]
            pixel_bytes[byte_index + 2] = pixel_color[2]
            byte_index += 3

    # Load in all the pixels to the pixel region at once
    pixel_region[0:width, 0:height] = pixel_bytes.tostring()

    img.add_layer(lyr, 0)
    img.filename = file.name
    return img


def load_rle(file):
    max_width = 512

    pdb.gimp_message('This is displayed as a message RLE')
    img = gimp.Image(1, 1, RGB)
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
