import os
from xml.sax import parse as parse_xml
from xml.sax.handler import ContentHandler

#"Id";"Designator";"Footprint";"Quantity";"Designation";"Supplier and ref";

class Component():
    def __init__(self, ref = "", value = "", footprint = "", quantity = 1):
        self.ref = ref
        self.value = value
        self.footprint = footprint
        self.quantity = quantity
        self.fitted = True

    def __repr__(self):
        return f"<component {self.ref}; {self.value}; {self.footprint}; {self.quantity}>"

class BomInfo(ContentHandler):

    def __init__(self):
        self._element = None
        self._component = None
        self.components = []
    
    def startElement(self, name: str, attr: dict[str, str]):
        self._element = name
        if name == "comp":
            self._component = Component(attr["ref"])
            self.components.append(self._component)
        elif name == "property" and self._component:
            if attr["name"] == "dnp":
                self._component.fitted = False

    def endElement(self, name: str):
        if name == "comp":
            self._component = None
        self._element = None
    
    def characters(self, content: str):
        if self._component:
            if self._element == "value":
                self._component.value = content
            elif self._element == "footprint":
                if ':' in content:
                    lib, content = content.split(':', maxsplit=1)
                self._component.footprint = content

    def get_components(self) -> list[Component]:
        return self.components

def group_components(components: list[Component]) -> list[Component]:
    groups = {}
    for component in components:
        key = f"{component.footprint}:{component.value}"
        if key not in groups:
            groups[key] = {
                "footprint": component.footprint,
                "refs": [],
                "value": component.value,
                "quantity": 0
            }
        groups[key]["refs"].append(component.ref)
        groups[key]["quantity"] += component.quantity
    return [
        Component(",".join(g["refs"]), g["value"], g["footprint"], g["quantity"]) for g in groups.values()
    ]

def select_fitted(components: list[Component], fitted: bool = True) -> list[Component]:
    return [ c for c in components if c.fitted == fitted ]

def sort_components(components: list[Component]) -> list[Component]:
    return sorted(components, key=lambda x: x.ref )

def write_csv(filename: str, components: list[Component]):
    with open(filename, "w") as f:

        def write_line(items: list[any]):
            f.write( ",".join([(str(item) if type(item) is int else f'"{item}"' ) for item in items]) + "\n" )

        write_line(["Id", "Value", "Designator", "Quantity", "Footprint"])
        
        for i, c in enumerate(components):
            write_line([ i+1, c.value, c.ref, c.quantity, c.footprint ])

def load_components(input_xml: str) -> list[Component]:
    info = BomInfo()
    parse_xml(input_xml, info)
    return info.get_components()

def create_bom(components: list[Component], output_csv: str):
    components = select_fitted(components, True)
    components = group_components(components)
    components = sort_components(components)
    write_csv(output_csv, components)

def get_dnf_list(components: list[Component]) -> list[str]:
    components = select_fitted(components, False)
    return [ c.ref for c in components ]

if __name__ == "__main__":
    import sys
    file_path = sys.argv[1]
    components = load_components(file_path + ".xml")
    create_bom(components, file_path + ".csv")