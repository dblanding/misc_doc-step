#!/usr/bin/env python
#
# lesson12.py
# copyright 2022 Doug Blanding (dblanding@gmail.com)
# Intended to be a conversion to PythonOCC from the original C++ code
# presented in the video tutorial Lesson 12: CAD assemblies with OpenCascade:
# https://www.youtube.com/watch?v=NMs7GtvsJ6g&list=PL_WFkJrQIY2iVVchOPhl77xl432jeNYfQ&index=10&t=1066s
# This video is one in a series of Open Cascade Lessons at Quaoar's Workshop:
# https://www.youtube.com/playlist?list=PL_WFkJrQIY2iVVchOPhl77xl432jeNYfQ
#
# As it turns out, PythonOCC has already got this functionality built into
# some of its modules, so all that needs to be done is to use these modules.
#     * Read and parse the step file into located shapes
#     * AIS_InteractiveContext display of located shapes
#
# It's actually available as one of the PythonOCC demo examples
# core_load_step_with_colors.py
#

from OCC.Extend.DataExchange import read_step_file_with_names_colors
from OCC.Display.SimpleGui import init_display

filename = "/home/doug/step-files/as1-oc-214.stp"
shapes_labels_colors = read_step_file_with_names_colors(filename)

# init graphic display
display, start_display, add_menu, add_function_to_menu = init_display()

for shpt_lbl_color in shapes_labels_colors:
    label, c = shapes_labels_colors[shpt_lbl_color]
    display.DisplayColoredShape(shpt_lbl_color, color=c)
start_display()