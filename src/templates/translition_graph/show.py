from jinja2 import Environment, FileSystemLoader, Template


class TransitionGraphRenderer:
    __template: Template
    __environment: Environment

    def __init__(self) -> None:
        # little workaround for notebooks. @TODO: think how to avoid that. Vladimir Makhanov
        import sys

        if any("retentioneering-tools-new-arch/examples" in x for x in sys.path):
            self.__environment = Environment(loader=FileSystemLoader("../src/templates/translition_graph"))
        else:
            self.__environment = Environment(loader=FileSystemLoader("src/templates/translition_graph"))

        self.__body_template = self.__environment.get_template("body.html")
        self.__full = self.__environment.get_template("full.html")
        self.__init = self.__environment.get_template("init.html")
        self.__inner_iframe = self.__environment.get_template("inner_iframe.html")

    def body(self, **kwargs) -> str:
        return self.__body_template.render(**kwargs)

    def full(self, **kwargs) -> str:
        return self.__full.render(**kwargs)

    def init(self, **kwargs) -> str:
        return self.__init.render(**kwargs)

    def inner_iframe(self, **kwargs) -> str:
        return self.__inner_iframe.render(**kwargs)

    def graph_stype(self) -> str:
        from .graph_style import style
        return style
