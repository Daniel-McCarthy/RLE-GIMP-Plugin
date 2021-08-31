# RLE-GIMP-Plugin
 GIMP plugin for the Neversoft .rle 16 bit image format.

 The state of this plugin is very work in progress and in development.
 The .rle and .bmr formats are 16 bit images using an ARGB1555 color format
 used in Neversoft's Spiderman 1 & 2, Apocalypse, and THPS.
 
This plugin allows opening .bmr (raw bitmaps), and .rle (run length encoded) images
from these games.

# Installing the plugin for GIMP
This plugin is written in Python 2 for GIMP v. 2.10. The script can be installed simply by copying the `file-rle.py` file to your plugin folder.
For Windows this can be:
- *`C:\Users\<Name>\Program Files\GIMP 2\lib\gimp\2.0\plug-ins`*
- *`C:\Users\<Name>\AppData\Roaming\GIMP\<2.10 or other version>\plug-ins`*
- A custom location set in `Settings > Folders > Plug-in Folders`.
