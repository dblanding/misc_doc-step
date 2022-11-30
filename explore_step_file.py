#!/usr/bin/env python
#
# Copyright 2022 Doug Blanding (dblanding@gmail.com)
#
# This file enables the convenient loading of STEP files
# allowing for simultaneously:
#   * Examination of their label hierarchy
#   * Display of the resulting colored model
# It is based heavily on the file DataExchange.py at
# https://github.com/tpaviot/pythonocc-core/blob/master/src/Extend/DataExchange.py
# The code has been modified to make it convenient to use
# and convenient to toggle 'verbose' mode.
#

from OCC.Core.TCollection import TCollection_AsciiString
from OCC.Core.TDF import TDF_Tool
from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool_ColorTool
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TCollection import TCollection_ExtendedString
from OCC.Core.TDF import TDF_Label, TDF_LabelSequence
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.XCAFApp import XCAFApp_Application_GetApplication
from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool_ShapeTool
from OCC.Display.SimpleGui import init_display
from OCC.Core.TDataStd import TDataStd_Name
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB


class DocModel():
    """Maintain 3D CAD model in OCAF TDocStd_Document format.

    Generates self.part_dict and self.label_dict by parsing self.doc.
    """

    def __init__(self):
        self.doc = self.create_doc()
        # To be used by redraw()
        self.part_dict = {}  # {uid: {keys: 'shape', 'name', 'color', 'loc'}}
        # To be used to construct treeView & access labels
        self.label_dict = {}  # {uid: {keys: 'entry', 'name', 'parent_uid', 'is_assy'}}
        self._share_dict = {}  # {entry: highest_serial_nmbr_used}
        self._parent_uid_stack = [None,]  # uid of parent lineage (topmost first)

    def create_doc(self):
        """Create XCAF doc with an empty assembly at entry 0:1:1:1.

        This is done only once in __init__."""

        # Create the application and document with empty rootLabel
        title = "Main document"
        doc = TDocStd_Document(TCollection_ExtendedString(title))
        app = XCAFApp_Application_GetApplication()
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
        shape_tool = XCAFDoc_DocumentTool_ShapeTool(doc.Main())
        color_tool = XCAFDoc_DocumentTool_ColorTool(doc.Main())
        # type(doc.Main()) = <class 'OCC.Core.TDF.TDF_Label'>
        # 0:1 doc.Main().EntryDumpToString()
        # 0:1:1   shape_tool is at this label entry
        # 0:1:2   color_tool at this entry
        # 0:1:1:1 rootLabel created at this entry
        rootLabel = shape_tool.NewShape()
        self.set_label_name(rootLabel, "Top")
        return doc

    def load_stp(self, filename):
        """Get XCAF document from STEP file and assign it directly to self.doc.

        """

        if not filename:
            print("Load step cancelled")
            return
        # create a handle to a document
        doc = TDocStd_Document(TCollection_ExtendedString("Step-doc"))
        step_reader = STEPCAFControl_Reader()
        step_reader.SetColorMode(True)
        step_reader.SetNameMode(True)
        status = step_reader.ReadFile(filename)
        if status == IFSelect_RetDone:
            step_reader.Transfer(doc)
        self.doc = doc
        # Build new self.part_dict & self.label_dict
        self.parse_doc()

    def parse_doc(self, verbose=False):
        """Return located shapes
        Generate new self.part_dict & self.label_dict.

        part_dict (dict of dicts) is used primarily for 3D display
        part_dict = {uid: {'located_shape': ,
                            'name': ,
                            'color': ,
                             }}
        label_dict (dict of dicts) is used primarily for tree view display
        label_dict = {uid:   {'entry': ,
                            'name': ,
                            'parent_uid': ,
                            'is_assy': }}
        """

        verbose = verbose
        shape_tool = XCAFDoc_DocumentTool_ShapeTool(self.doc.Main())
        color_tool = XCAFDoc_DocumentTool_ColorTool(self.doc.Main())

        cnt = 0
        lvl = 0
        output_shapes = {}
        locs = []

        def _get_uid_from_entry(entry):
            """Generate uid from label entry. format: entry + '.' + integer """
            if entry in self._share_dict:
                value = self._share_dict[entry]
            else:
                value = -1
            value += 1
            # update serial number in self._share_dict
            self._share_dict[entry] = value
            uid = entry + '.' + str(value)
            return uid

        def _get_sub_shapes(lab, loc):
            """(Starting with 'lab' = label of first free shape at root)

            * Examine entire document:
                * look through all free shapes at root
                    * If IsAssembly(lab):
                        * Examine each component 'label'
                        * For each component (label):
                        * If IsReference(label):
                            * Find label to which it refers 'label_reference'
                            * Get location loc = GetLocation(label)
                            * Append loc to locs
                            * Recursively call this function with (label_reference, loc)
                            * locs.pop()
                    * elif IsSimpleShape(lab):
                        * get prototype shape
                        * get color 'c'
                        * get composed location 'loc' (effect of all enclosing assemblies)
                        * Build located shape for display 'shape_disp'
                        * If 'lab' has subshapes:
                        * find and process subshapes
            """
            nonlocal cnt, lvl
            entry = TCollection_AsciiString()
            TDF_Tool.Entry(lab, entry)
            text_entry = entry.ToCString()
            uid = _get_uid_from_entry(text_entry)
            name = lab.GetLabelName()
            if verbose:
                cnt += 1
                print("\n[%d] level %d, handling LABEL %s (uid: %s), (parent_uid: %s)\n" % (
                    cnt, lvl, name, uid, self._parent_uid_stack[-1])
                      )
                print()
                print(lab.DumpToString())
                print()
                print("Is Assembly    :", shape_tool.IsAssembly(lab))
                print("Is Free        :", shape_tool.IsFree(lab))
                print("Is Shape       :", shape_tool.IsShape(lab))
                print("Is Compound    :", shape_tool.IsCompound(lab))
                print("Is Component   :", shape_tool.IsComponent(lab))
                print("Is SimpleShape :", shape_tool.IsSimpleShape(lab))
                print("Is Reference   :", shape_tool.IsReference(lab))

                users = TDF_LabelSequence()
                users_cnt = shape_tool.GetUsers(lab, users)
                if verbose:
                    print("Nr Users       :", users_cnt)

            l_subss = TDF_LabelSequence()
            shape_tool.GetSubShapes(lab, l_subss)
            if verbose:
                print("Nb subshapes   :", l_subss.Length())
            l_comps = TDF_LabelSequence()
            shape_tool.GetComponents(lab, l_comps)
            if verbose:
                print("Nb components  :", l_comps.Length())
                print()
            if verbose:
                print("Name :", name)

            parent_uid = self._parent_uid_stack[-1]
            if shape_tool.IsAssembly(lab):
                l_dict = {'entry': text_entry,
                          'name': name,
                          'parent_uid': parent_uid,
                          'is_assy': True}
                self.label_dict[uid] = l_dict
                self._parent_uid_stack.append(uid)
                l_c = TDF_LabelSequence()
                shape_tool.GetComponents(lab, l_c)
                for i in range(l_c.Length()):
                    label = l_c.Value(i + 1)
                    if shape_tool.IsReference(label):
                        cmpnt_entry = TCollection_AsciiString()
                        TDF_Tool.Entry(label, cmpnt_entry)
                        text_cmpnt_entry = cmpnt_entry.ToCString()
                        uid = _get_uid_from_entry(text_cmpnt_entry)
                        cmpnt_name = label.GetLabelName()
                        if verbose:
                            msg = f"\n########  component label [{text_cmpnt_entry}] {cmpnt_name} "
                        label_reference = TDF_Label()
                        shape_tool.GetReferredShape(label, label_reference)
                        ref_shp_entry = TCollection_AsciiString()
                        TDF_Tool.Entry(label_reference, ref_shp_entry)
                        text_ref_shp_entry = ref_shp_entry.ToCString()
                        ref_shp_name = label_reference.GetLabelName()
                        if verbose:
                            msg = msg + f"refers to prototype label [{text_ref_shp_entry}] {ref_shp_name}"
                            print(msg)
                            print()
                            print("    Is Assembly    :", shape_tool.IsAssembly(label))
                            print("    Is Free        :", shape_tool.IsFree(label))
                            print("    Is Shape       :", shape_tool.IsShape(label))
                            print("    Is Compound    :", shape_tool.IsCompound(label))
                            print("    Is Component   :", shape_tool.IsComponent(label))
                            print("    Is SimpleShape :", shape_tool.IsSimpleShape(label))
                            print("    Is Reference   :", shape_tool.IsReference(label))
                            print()
                        loc = shape_tool.GetLocation(label)
                        if verbose:
                            print("    loc          :", loc)
                            trans = loc.Transformation()
                            print("    tran form    :", trans.Form())
                            rot = trans.GetRotation()
                            print("    rotation     :", rot)
                            print("    X            :", rot.X())
                            print("    Y            :", rot.Y())
                            print("    Z            :", rot.Z())
                            print("    W            :", rot.W())
                            tran = trans.TranslationPart()
                            print("    translation  :", tran)
                            print("    X            :", tran.X())
                            print("    Y            :", tran.Y())
                            print("    Z            :", tran.Z())

                        locs.append(loc)
                        lvl += 1
                        if verbose:
                            print(">>>>")
                        _get_sub_shapes(label_reference, loc)
                        lvl -= 1
                        if verbose:
                            print("<<<<")
                        locs.pop()
                        # Trim self._parent_uid_stack when lvl decreases
                        while len(self._parent_uid_stack) > lvl+2:
                            self._parent_uid_stack.pop()

            elif shape_tool.IsSimpleShape(lab):
                l_dict = {'entry': text_entry,
                          'name': name,
                          'parent_uid': parent_uid,
                          'ref_entry': None,
                          'is_assy': False}
                self.label_dict[uid] = l_dict
                if verbose:
                    print("\n########  simpleshape label :", lab)
                shape = shape_tool.GetShape(lab)
                if verbose:
                    print("    all ass locs   :", locs)

                loc = TopLoc_Location()
                for l in locs:
                    if verbose:
                        print("    take loc       :", l)
                    loc = loc.Multiplied(l)

                if verbose:
                    trans = loc.Transformation()
                    print("    FINAL loc    :")
                    print("    tran form    :", trans.Form())
                    rot = trans.GetRotation()
                    print("    rotation     :", rot)
                    print("    X            :", rot.X())
                    print("    Y            :", rot.Y())
                    print("    Z            :", rot.Z())
                    print("    W            :", rot.W())
                    tran = trans.TranslationPart()
                    print("    translation  :", tran)
                    print("    X            :", tran.X())
                    print("    Y            :", tran.Y())
                    print("    Z            :", tran.Z())
                c = Quantity_Color(0.5, 0.5, 0.5, Quantity_TOC_RGB)  # default color
                color_set = False
                if (
                    color_tool.GetInstanceColor(shape, 0, c)
                    or color_tool.GetInstanceColor(shape, 1, c)
                    or color_tool.GetInstanceColor(shape, 2, c)
                ):
                    color_tool.SetInstanceColor(shape, 0, c)
                    color_tool.SetInstanceColor(shape, 1, c)
                    color_tool.SetInstanceColor(shape, 2, c)
                    color_set = True
                    n = c.Name(c.Red(), c.Green(), c.Blue())
                    print(
                        "    instance color Name & RGB: ",
                        c,
                        n,
                        c.Red(),
                        c.Green(),
                        c.Blue(),
                    )

                if not color_set:
                    if (
                        color_tool.GetColor(lab, 0, c)
                        or color_tool.GetColor(lab, 1, c)
                        or color_tool.GetColor(lab, 2, c)
                    ):

                        color_tool.SetInstanceColor(shape, 0, c)
                        color_tool.SetInstanceColor(shape, 1, c)
                        color_tool.SetInstanceColor(shape, 2, c)

                        n = c.Name(c.Red(), c.Green(), c.Blue())
                        if verbose:
                            print(
                                "    shape color Name & RGB: ",
                                c,
                                n,
                                c.Red(),
                                c.Green(),
                                c.Blue(),
                            )

                # Position the shape to display
                shape_disp = BRepBuilderAPI_Transform(shape, loc.Transformation()).Shape()

                # Update dictionaries
                if not shape_disp in output_shapes:
                    output_shapes[shape_disp] = [lab.GetLabelName(), c]
                p_dict = {'shape': shape_disp, 'name': name, 'color': c}
                self.part_dict[uid] = p_dict

                # Visit and display subshapes (if any)
                for i in range(l_subss.Length()):
                    lab_subs = l_subss.Value(i + 1)
                    if verbose:
                        print("\n########  simpleshape subshape label :", lab)
                    shape_sub = shape_tool.GetShape(lab_subs)

                    c = Quantity_Color(0.5, 0.5, 0.5, Quantity_TOC_RGB)  # default color
                    color_set = False
                    if (
                        color_tool.GetInstanceColor(shape_sub, 0, c)
                        or color_tool.GetInstanceColor(shape_sub, 1, c)
                        or color_tool.GetInstanceColor(shape_sub, 2, c)
                    ):
                        color_tool.SetInstanceColor(shape_sub, 0, c)
                        color_tool.SetInstanceColor(shape_sub, 1, c)
                        color_tool.SetInstanceColor(shape_sub, 2, c)
                        color_set = True
                        n = c.Name(c.Red(), c.Green(), c.Blue())
                        if verbose:
                            print(
                                "    instance color Name & RGB: ",
                                c,
                                n,
                                c.Red(),
                                c.Green(),
                                c.Blue(),
                            )

                    if not color_set:
                        if (
                            color_tool.GetColor(lab_subs, 0, c)
                            or color_tool.GetColor(lab_subs, 1, c)
                            or color_tool.GetColor(lab_subs, 2, c)
                        ):
                            color_tool.SetInstanceColor(shape, 0, c)
                            color_tool.SetInstanceColor(shape, 1, c)
                            color_tool.SetInstanceColor(shape, 2, c)

                            n = c.Name(c.Red(), c.Green(), c.Blue())
                            print(
                                "    shape color Name & RGB: ",
                                c,
                                n,
                                c.Red(),
                                c.Green(),
                                c.Blue(),
                            )
                    shape_to_disp = BRepBuilderAPI_Transform(
                        shape_sub, loc.Transformation()
                    ).Shape()
                    # position the subshape to display
                    if not shape_to_disp in output_shapes:
                        output_shapes[shape_to_disp] = [lab_subs.GetLabelName(), c]

        def _get_shapes():
            labels = TDF_LabelSequence()
            shape_tool.GetFreeShapes(labels)

            if verbose:
                print()
                print("Number of free shapes at root :", labels.Length())
                print()
            for i in range(labels.Length()):
                root_item = labels.Value(i + 1)
                _get_sub_shapes(root_item, None)

        _get_shapes()
        return output_shapes

    def set_label_name(self, label, name):
        TDataStd_Name.Set(label, TCollection_ExtendedString(name))


if __name__ == "__main__":
    # init graphic display
    display, start_display, add_menu, add_function_to_menu = init_display()

    fname = "./step/chassis-plus-root.step"

    # Create DocModel instance
    dm = DocModel()
    dm.load_stp(fname)
    located_shapes = dm.parse_doc(verbose=True)
    print(f"{len(dm.part_dict)=}")
    print(f"{len(dm.label_dict)=}")
    for shape, [name, color] in located_shapes.items():
        display.DisplayColoredShape(shape, color, update=True)
    start_display()