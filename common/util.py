from github.GithubException import UnknownObjectException
from werkzeug.exceptions import BadRequest

from .exceptions import InvalidArgument, InvalidData
from .users.access_token import AccessToken
from .users.user import User, UserBy
from .users.package import Package
from .argument import Argument

from github.Repository import Repository
from github.GitRelease import GitRelease

from dotenv import load_dotenv
from github import Github
from flask import request
from typing import Any

import mysql.connector
import hashlib
import json
import time
import os

with open("config.json", "r") as f: CONFIG = json.load(f)
with open("classifiers.json", "r") as f: CLASSIFIERS = json.load(f)

def structure_argument(**data) -> tuple: return tuple(data.items())
ROUTES_ARGUMENTS = {
    "register": {"username": Argument(type=str, max_length=100), "password": Argument(type=str)},
    "login": {"username": Argument(type=str), "password": Argument(type=str)},
    "upload_package": {
        "access_token": Argument(type=str),
        
        "name": Argument(type=str, max_length=50),
        "author_email": Argument(type=str, max_length=256),
        "version": Argument(type=str, max_length=256),

        "description": Argument(type=str, max_length=256),
        "description_file": Argument(type=str, max_length=256),

        "requirements": Argument(type=list, max_length=10),
        "repository": Argument(type=str, max_length=200),
        "license": Argument(type=str, max_length=10),

        "classifiers": Argument(type=list, max_length=20),
        "entry_points": Argument(type=list, max_length=100, required=False, iter_structure={structure_argument(type=str, max_length=256, required=False): [structure_argument(type=str, max_length=256)]})
    },
    "delete_package_release": {
        "access_token": Argument(type=str),
        "name": Argument(type=str, max_length=50),
        "version": Argument(type=str, max_length=256)
    },
    "delete_package": {"access_token": Argument(type=str), "name": Argument(type=str, max_length=50)},
    "get_download": {"name": Argument(type=str, max_length=50), "version": Argument(type=str, max_length=256, required=False)},
    "get_package": {"name": Argument(type=str, max_length=50), "version": Argument(type=str, max_length=256, required=False)}
}

load_dotenv()
database = mysql.connector.connect(host=os.getenv("DATABASE_HOST"), password=os.getenv("DATABASE_PASSWORD"), user=CONFIG["DATABASE_USER"], database=CONFIG["DATABASE"])
cursor = database.cursor(dictionary=True)

github = Github(os.getenv("GITHUB_TOKEN"))

#region Get arguments
def get_arguments(arguments : dict[str, Argument]) -> dict:
    try: data : dict = request.get_json()
    except BadRequest: raise InvalidArgument("Request must be JSON", 400)
    if not isinstance(data, dict): InvalidArgument("Data must be Dict", 400)

    for argument, validation in arguments.items():
        if not argument in data:
            if validation.required: raise InvalidArgument(f"Missing Argument: {argument}", 422)
            continue
        
        value = data[argument]
        if validation.iter_structure is not None and not __check_iter(value, validation.iter_structure): raise InvalidArgument(f"Stacture for argument {argument} must be: {validation.iter_structure_str}", 422)
        success, reason = __verify_argument(value, validation, argument)
        if not success: InvalidArgument(*reason)

    return data

def __check_iter(value : list | dict, structure : list | dict) -> bool:    
    if not isinstance(structure, tuple):
        try: currentCheck = next(iter(structure))
        except (TypeError, StopIteration):
            if not __verify_argument(value, structure, None)[0]: return False
    else: currentCheck = structure
    currentValidation = Argument.parse_obj(currentCheck)

    if isinstance(structure, tuple):
        if not isinstance(value, currentValidation.type): return False
    elif currentValidation.required and structure and not value:
        return False
    elif not isinstance(value, type(structure)):
        return False
    
    if isinstance(structure, dict):
        structure = structure[currentCheck]
        for itemKey, itemValue in value.items():
            argumentValid, = __verify_argument(itemKey, currentCheck, None)[:1]
            if not argumentValid: return False

            if not __check_iter(itemValue, structure): return False
    elif isinstance(structure, list):
        structure = structure[0]
        for item in value:
            argumentValid, = __check_iter(item, currentCheck, None)[:1]
            if not argumentValid: return False

            if not __check_iter(item, structure): return False

    return True

def __verify_argument(value : Any, validation : Argument | tuple, argument : str) -> tuple[bool, tuple[str, int] | None]:
    if not isinstance(validation, Argument): validation = Argument.parse_obj(validation)

    if not isinstance(value, validation.type): return False, (f"Argument {argument} must be type {validation.type.__name__}", 422)
    elif validation.max_length and len(value) > validation.max_length: return False, (f"Argument {argument} Too Long", 422)
    elif validation.min_length and len(value) < validation.min_length: return False, (f"Argument {argument} Too Short", 422)

    return True, None
#endregion

def check_login(token : str, fetchUser=False) -> tuple[bool, User]:
    token = token.encode("utf-8")
    hash = hashlib.sha512(token).hexdigest()

    cursor.execute("SELECT * FROM access_tokens WHERE token_hash=%s AND ip=%s AND user_agent=%s", (hash, request.remote_addr, request.headers.get("User-Agent")))
    token = cursor.fetchone()
    if not token: return False, None

    token = AccessToken.parse_obj(token)
    if token.created + 60 * 60 * 24 * 14 < time.time(): return False, None

    user = None
    if fetchUser: user = fetch_user(UserBy.ID, token.user_id)

    return True, user

#region Fetch from database
def fetch_user(by : str, value : str) -> User:
    if by == UserBy.USERNAME: cursor.execute("SELECT * from users WHERE username=%s", (value,))
    elif by == UserBy.ID: cursor.execute("SELECT * from users WHERE id=%s", (value,))

    user = cursor.fetchone()
    if not user: return

    return User.parse_obj(user)

def fetch_latest_package_release(name : str) -> Package:
    cursor.execute("SELECT * FROM packages WHERE name=%s AND latest=1", (name,))
    package = cursor.fetchone()
    
    if not package:
        cursor.execute("SELECT * FROM packages WHERE name=%s ORDER BY release_date DESC LIMIT 1", (name,))
        package = cursor.fetchone()
        if not package: return

    return Package.parse_obj(package)

def fetch_package_release(name : str, version : str) -> Package:
    cursor.execute("SELECT * FROM packages WHERE name=%s AND version=%s", (name, version))
    package = cursor.fetchone()
    if not package: return

    return Package.parse_obj(package)

def get_github(package : Package) -> tuple[bool, Repository]:
    try: repository = github.get_repo(package.repository)
    except UnknownObjectException:
        package.delete(cursor)
        database.commit()
        return False,None

    return True, repository

def get_github_release(package : Package) -> tuple[bool, GitRelease]:
    success, repository = get_github(package)
    if not success: return False, None

    try: release = repository.get_release(package.version)
    except UnknownObjectException:
        package.delete_release(cursor)
        database.commit()
        return False, None

    return True, release
#endregion

#region Parse to database
def parse_requirements_mysql(requirements : list, originPackage : Package, uploadedPackageID : int) -> list:
    mysqlRequirements = []
    for requirement in requirements:
        if not isinstance(requirement, str): raise InvalidData(f"Requirement Must be str", 400)
        requirement = requirement.split("==")
    
        package = requirement[0]
        if package == package: raise InvalidData("Requirement can't be the package you're uploading", 401)
        elif len(requirement) > 1:
            version = requirement[1]
            if not fetch_package_release(package, version): raise InvalidData(f"Requirement Package Not Found: {package}, With Version: {version}", 404)
        else:
            latestRequirementRelease = fetch_latest_package_release(package)
            if not latestRequirementRelease: raise InvalidData(f"Requirement Package Not Found: {package}", 404)
            version = latestRequirementRelease.version

        mysqlRequirements.append((uploadedPackageID, originPackage.name, package, version))
    
    return mysqlRequirements

def parse_classifiers_mysql(classifiers : list, originPackage : Package, uploadedPackageID : int):
    mysqlClassifiers = []
    for classifier in classifiers:
        if not isinstance(classifier, str): raise InvalidData(f"Classifier Must be str", 400)
        tree = classifier.split(" :: ")

        lastItem = CLASSIFIERS
        for item in tree:
            if not item in lastItem: raise InvalidData(f"Classifier Not Found: {classifier}", 404)
            lastItem = lastItem[item]

        mysqlClassifiers.append((uploadedPackageID, originPackage.name, classifier))
    return mysqlClassifiers
#endregion