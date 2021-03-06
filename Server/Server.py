import dbus
import dbus.exceptions
import flask

from typing import Optional, cast, Any, List, Dict, Union

from functools import wraps, partial
from flask import Flask, Response, render_template, request

from Server.Database import db_session, init_db
from Server.models import User, Ability
from werkzeug.exceptions import Forbidden, Unauthorized

_REGISTERED_ROUTES = {}  # type: Dict[str, Dict[str, Any]]


def register_route(route: Optional[str] = None, accepted_methods: Optional[List[str]] = None):
    """
    Simple decorator for class based views. It's probably hacking a bit around the default stuff of flask...
    :param route: url it needs to listen to.
    :param accepted_methods: What methods (GET, PUT, SET) are accepted?
    :return:
    """
    def inner(function):
        result_dict = {"func": function}
        if accepted_methods is None:
            result_dict["methods"] = ["GET"]
        else:
            result_dict["methods"] = accepted_methods
        _REGISTERED_ROUTES[route] = result_dict
        return function
    return inner


def requires_user_ability(ability: str):
    """
    Decorator that marks a given endpoint as needing an ability
    :param abilities:
    :return:
    """
    def wrapper(func):
        @wraps(func)
        def inner(*args, **kwargs):
            user_id = request.args.get("userID")
            if not user_id:
                raise Unauthorized("You need to provide some credentials first!")
            user = User.query.filter_by(card_id = user_id).first()
            if not user:
                raise Forbidden("User is unknown")

            desired_ability = Ability.query.filter_by(name = ability).first()

            if desired_ability in user.abilities:
                return func(*args, **kwargs)

            raise Forbidden("User is not allowed to do this!")

        return inner
    return wrapper


class Server(Flask):
    STATIC_LOCATION = ""
    
    def __init__(self, *args, **kwargs) -> None:
        if "import_name" not in kwargs:
            kwargs.setdefault('import_name', __name__)

        super().__init__(*args, **kwargs)

        # Register the routes from the decorator
        self.add_url_rule(rule="/<path:path>", view_func=self.staticHost)
        for route, config_options in _REGISTERED_ROUTES.items():
            partial_fn = partial(config_options["func"], self)
            # We must set a name to for this partial function.
            cast(Any, partial_fn).__name__ = config_options["func"].__name__
            self.add_url_rule(route, view_func = partial_fn, methods = config_options["methods"])

        self._bus = dbus.SessionBus()

        self.register_error_handler(dbus.exceptions.DBusException, self._dbusExceptionHandler)

        # This is needed for the sqlalchemy database
        self.teardown_appcontext(self._shutdownSession)

        self._nodes = None
        self._modifiers = None
        init_db()

    @staticmethod
    def _shutdownSession(exception):
        db_session.remove()

    def getNodeDBusObject(self):
        self._setupNodeDBUS()
        return self._nodes

    def getModifierDBusObject(self):
        self._setupModifierDBUS()
        return self._modifiers

    def _setupModifierDBUS(self) -> None:
        self._initModifierDBUS()
        try:
            self._modifiers.checkAlive()  # type: ignore
        except dbus.exceptions.DBusException:
            self._modifiers = None
            # It could be that the service was rebooted, so we should try this again.
            self._initModifierDBUS()

    def _initModifierDBUS(self) -> None:
        """
        Create DBUS object.
        """
        if self._modifiers is None:
            try:
                self._modifiers = self._bus.get_object('com.frivengi.modifiers', '/com/frivengi/modifiers')
            except dbus.exceptions.DBusException as exception:
                self._modifiers = None
                raise exception

    def _dbusExceptionHandler(self, exception: dbus.exceptions.DBusException) -> Response:
        if exception.get_dbus_name() == "org.freedesktop.DBus.Error.ServiceUnknown":
            # We couldn't find the server on the other side. No need to log it more
            self._nodes = None
        else:
            self.logger.warning("An exception occured %s" % str(exception))
        return Response(str(exception),
                        status=500)

    def _setupNodeDBUS(self) -> None:
        self._initNodeDBUS()
        try:
            self._nodes.checkAlive()  # type: ignore
        except dbus.exceptions.DBusException:
            self._nodes = None
            # It could be that the service was rebooted, so we should try this again.
            self._initNodeDBUS()

    def _initNodeDBUS(self) -> None:
        """
        Create DBUS object.
        """
        if self._nodes is None:
            try:
                self._nodes = self._bus.get_object('com.frivengi.nodes', '/com/frivengi/nodes')
            except dbus.exceptions.DBusException as exception:
                self._nodes = None
                raise exception

    def staticHost(self, path: str) -> Any:
        """
        Used for providing files that are hosted in maintenance / admin pages
        :param path:
        :return:
        """
        return flask.send_from_directory(self.STATIC_LOCATION, path)

    @register_route("/")
    def renderStartPage(self):
        self._setupNodeDBUS()
        display_data = []
        return render_template("index.html", data = display_data)

    @register_route("/userManagement")
    def renderUserManagementPage(self):
        return render_template("userManagement.html")

    @register_route("/controllerManagement")
    def renderControllerManagementPage(self):
        return render_template("controllerManagement.html")

    @register_route("/users/")
    @requires_user_ability("see_users")
    def listAllUsers(self):
        all_users = User.query.all()
        return Response(flask.json.dumps([user.name for user in all_users]), status=200, mimetype="application/json")

    @register_route("/startTick", ["POST"])
    def startTick(self) -> Response:
        self._setupNodeDBUS()
        self._nodes.doTick()  # type: ignore

        return Response(flask.json.dumps({"message": ""}), status=200, mimetype="application/json")


if __name__ == "__main__":
    Server().run(debug=True)
