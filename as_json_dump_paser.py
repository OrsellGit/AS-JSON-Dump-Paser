"""
A JSON parser for parsing the dumped AngelScript JSON files from Strata Source for turning it into a 
"as.predefined" file for use with the AngelScript Language Server Visual Studio Code Extension.
https://marketplace.visualstudio.com/items?itemName=sashi0034.angel-lsp

Usage: "python as_json_dump_paser.py input.json"

Author: Orsell/OrsellGit
"""

import json, sys, os

'''
    This map is used to switch out the operator overloads defined with the proper AngelScript defined versions.
    Not all the operators are defined here because not all of them have been used, only common ones are defined.
    Update and add new operators when needed.
''' 
OPERATOR_MAP: dict[str, str] = {
    
    # Prefixed Unary Operators
    "operator-()":  "opNeg()",
    "operator~":    "opCom",
    "operator++()": "opPreInc()",
    "operator--()": "opPreDec()",

    # Postfixed Unary Operators
    "operator++": "opPostInc",
    "operator--": "opPostDec",

    # Comparison Operators
    "operator==": "opEquals",
    "operator!=": "opEquals", # Exact same as opEquals because the underlying implementation is expected to do the same just negated.
    "operator<":  "opCmp",    # Unsure how the underlying C++ code handles comparisons, so I am just gonna trust the AngelScript docs on this fact that they all work with the same operator name.
    "operator<=": "opCmp",
    "operator>":  "opCmp",
    "operator>=": "opCmp",

    # Assignment Operators
    "operator=":  "opAssign",
    "operator+=": "opAddAssign",
    "operator-=": "opSubAssign",
    "operator*=": "opMulAssign",
    "operator/=": "opDivAssign",
    "operator@=": "opHndlAssign",

    # Binary Operations
    "operator+": "opAdd",
    "operator-": "opSub",
    "operator*": "opMul",
    "operator/": "opDiv",

    # Index Operators
    "operator[]": "opIndex",
}

def NormalizeOperator(declaration: str) -> str:
    """
    Operator overloads dumped by the game are not in the proper AngelScript form, swap them out with the correct version using the map.
    
    :param declaration: Declaration that needs to be fixed.
    :type declaration: str
    :return: Fixed operator overload.
    :rtype: str
    """

    # For each operator in the map list, check if the declaration matches one then replace it.
    for op, replacement in OPERATOR_MAP.items():
        if (op in declaration):
            return declaration.replace(op, replacement, 1)
    return declaration


# ------------------------------------------------------------
# Namespace helpers
# ------------------------------------------------------------

def Indent(depth: int = 0) -> str:
    return "\t" * depth


def SplitNamespace(ns: str) -> list[str]:
    """
    Split up the namespaces of a function declaration so they can be defined correctly.
    
    :param ns: Namespace to split.
    :type ns: str
    :return: List of namespaces.
    :rtype: list[str]
    """

    # Return a list of the spit up namespaces, else just a empty list.
    return ns.split("::") if ns else []


def StripNamespaceFromDecl(declaration: str, namespacePath: str) -> str:
    """
    Remove the fully-qualified namespace prefix from a declaration.

    This is required when emitting symbols inside a namespace block,
    since AngelScript does not allow qualified names inside namespace scopes.

    :param declaration: Declaration string.
    :type declaration: str
    :param namespacePath: Full namespace path being emitted.
    :type namespacePath: str
    :return: Declaration without namespace qualification.
    :rtype: str
    """

    # If there is no namespace, then return the declaration as is, else strip out the namespace from the declaration.
    if (not namespacePath):
        return declaration
    prefix = namespacePath + "::"
    return declaration.replace(prefix, "", 1)


def BuildNamespaceTree(items: list[dict]) -> dict:
    """
    Build a hierarchical namespace tree from a list of JSON objects.

    Each node in the tree represents a namespace and may contain child namespaces
    as well as a list of objects stored under the special `__items__` key.

    :param items: List of JSON objects.
    :type items: list[dict]
    :return: Nested namespace tree structure.
    :rtype: dict
    """

    tree: dict = {}

    # BuildNamespaceTree assumes that what JSON objects we have could be in a namespace and simply checks if a namespace is defined.
    # If there isn't then it just goes on as normal as there would be no seperate parts to deal with caused by a declared namespace.
    for item in items:
        ns = item.get("namespace") or ""
        parts = SplitNamespace(ns)

        node = tree
        for part in parts:
            node = node.setdefault(part, {})

        node.setdefault("__items__", []).append(item)

    return tree


def EmitNamespaceTree(file, tree, writeFn: function, namespacePath = "", depth = 0) -> None:
    """
    Recursively emit a namespace tree to an AngelScript predefined file.

    This function walks the namespace tree depth-first, opening and closing
    AngelScript namespace blocks as required, and emitting symbols using the provided writer function.

    :param file: File to write to.
    :param tree: Namespace tree structure.
    :param writeFn: Writer function.
    :param namespacePath: Namespace path.
    :type namespacePath: str
    """

    for key, subtree in tree.items():
        if (key == "__items__"):
            for item in subtree:
                writeFn(file, item, namespacePath, depth)
            continue

        newPath = f"{namespacePath}::{key}" if namespacePath else key

        file.write(f"{Indent(depth)}namespace {key}\n")
        file.write(f"{Indent(depth)}{{\n")

        # Yes, there recursion going on here, but unless there is many namespaces in the namespaces "tree" structure, this shouldn't be too bad.
        EmitNamespaceTree(file, subtree, writeFn, newPath, depth + 1)

        file.write(f"{Indent(depth)}}}\n\n")
    file.write("\n")


# ------------------------------------------------------------
# Writers
# ------------------------------------------------------------

def WriteEnum(file, enum, namespacePath = None, depth = 0) -> None:
    """
    Write a enum to file from JSON to AngelScript.
    
    :param file: File to write to.
    :param enum: Enum JSON object that will be written to file.
    :param namespacePath: Unused for enums.
    """

    name = enum["name"]
    values = enum["value"]

    file.write(f"{Indent(depth)}enum {name}\n{Indent(depth)}{{\n")
    for key, val in values.items():
        file.write(f"{Indent(depth + 1)}{key} = {val},\n")
    file.write(f"{Indent(depth)}}}\n\n")


def WriteFunction(file, func, namespacePath = None, depth = 0) -> None:
    """
    Write a global or namespaced AngelScript function declaration.

    If the function belongs to a namespace, the namespace qualifier is
    stripped from the declaration before emission.

    :param file: File to write to.
    :param func: Function JSON object that will be written to file.
    :param namespacePath: Current namespace path.
    """

    decl = func["declaration"]

    if namespacePath:
        decl = StripNamespaceFromDecl(decl, namespacePath)
    
    file.write(f"{Indent(depth)}{decl};\n")


def WriteProperty(file, prop, namespacePath = None, depth = 0) -> None:
    """
    Write a global or namespaced AngelScript property declaration.

    :param file: File to write to.
    :param prop: Property JSON object that will be written to file.
    :param namespacePath: Current namespace path.
    """

    const = "const " if prop.get("is_const") else ""
    type = prop["type"]
    name = prop["name"]

    file.write(f"{Indent(depth)}{const}{type} {name};\n")


def WriteType(file, typ, namespacePath = None, depth = 0) -> None:
    """
    Write an type or class with or without template type definition.

    :param file: File to write to.
    :param typ: Type JSON object that will be written to file.
    :param namespacePath: Current namespace path.
    """

    name = typ["name"]

    # Templates
    templateParameter = typ.get("template_parameter")
    if (templateParameter):
        params = ", ".join(p["name"] for p in templateParameter)
        className = f"{name}<{params}>"
    else:
        className = name

    # Inheritance
    base = typ.get("base_type")
    if (base):
        baseName = base["name"]
        file.write(f"{Indent(depth)}class {className} : {baseName}\n{{\n")
    else:
        file.write(f"{Indent(depth)}class {className}\n{{\n")

    # Listing all methods of the class.
    for method in typ.get("method", []):
        decl = NormalizeOperator(method["declaration"])
        doc = method.get("documentation")

        if (doc): # TODO: Replace with Doxygen type documentation.
            for line in doc.splitlines():
                file.write(f"{Indent(depth + 1)}// {line}\n")

        file.write(f"{Indent(depth + 1)}{decl};\n")

    file.write(f"{Indent(depth)}}}\n\n")


# ------------------------------------------------------------
# Main Functions
# ------------------------------------------------------------

def JSONToAS(jsonPath: str) -> None:
    """
    Convert the JSON file to an "as.predefined" AngelScript file for the AngelScript Language Server to read.
    
    :param jsonPath: Path to the JSON file to convert.
    """

    with open(jsonPath, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open("as.predefined", "w", encoding="utf-8") as file:
        # Comment header for the as.predefined file.
        file.write("// The Classes, Functions, Enums, and other Types of the\n")
        file.write("// Portal 2: Community Edition's AngelScript Scripting System.\n\n")

        # Have to assume that the various types of objects have to have a namespace
        EmitNamespaceTree(file, BuildNamespaceTree(data.get("enum", [])), WriteEnum)
        EmitNamespaceTree(file, BuildNamespaceTree(data.get("function", [])), WriteFunction)
        EmitNamespaceTree(file, BuildNamespaceTree(data.get("property", [])), WriteProperty)
        EmitNamespaceTree(file, BuildNamespaceTree(data.get("type", [])), WriteType)

if (__name__ == "__main__"):
    if (len(sys.argv) != 2):
        print("Usage: python as_json_dump_paser.py input.json")
        sys.exit(1)

    inputDumpFile: str = sys.argv[1]

    # Back up any older as.predefined file as a just in case.
    if (os.path.exists("./as.predefined")):
        print("as.predefined already exists, backing up original file by copying and renaming with \".old\" extension.")
        if (os.path.exists("./as.predefined.old")):
            os.remove("./as.predefined.old")
        os.rename("./as.predefined", "./as.predefined.old")

    JSONToAS(inputDumpFile)
    print(f"Generated new \"as.predefined\" from \"{inputDumpFile}\" JSON file!")
