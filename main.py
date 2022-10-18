from github.GithubException import UnknownObjectException
from common.exceptions import InvalidArgument
from common.argument import Argument
from flask import request, jsonify
from common.util import *

import hashlib
import secrets
import flask
import uuid
import time

app = flask.Flask(__name__)

@app.route("/register", methods=["POST"])
def register():
    try: data = get_arguments(ROUTES_ARGUMENTS["register"])
    except InvalidArgument as e: return e.args
    username = data["username"]
    password = data["password"].encode("utf-8")
    
    if fetch_user(UserBy.USERNAME, username): return "Username already exists", 409

    if len(username) > 100: return "Username too long", 422
    elif not username: return "Username must not be empty", 422
    if len(password) < 5: return "Password too short", 422

    salt = uuid.uuid4().hex.encode("utf-8")
    hash = hashlib.sha512(password + salt).hexdigest()
    cursor.execute("INSERT INTO users (username, hash, salt) VALUES (%s, %s, %s)", (username, hash, salt))
    database.commit()
    
    return "Registered Account", 200

@app.route("/login", methods=["POST"])
def login():
    try: data = get_arguments(ROUTES_ARGUMENTS["login"])
    except InvalidArgument as e: return e.args
    username = data["username"]
    password = data["password"].encode("utf-8")

    user = fetch_user(UserBy.USERNAME, username)
    if not user: return "Incorrect username / password", 401
    elif hashlib.sha512(password + user.salt).hexdigest() != user.hash: return "Incorrect username / password", 401

    cursor.execute("DELETE FROM access_tokens WHERE user_id=%s", (user.id,))
    
    while True:
        token = secrets.token_hex().encode("utf-8")
        hash = hashlib.sha512(token).hexdigest()
        
        cursor.execute("SELECT * FROM access_tokens WHERE token_hash=%s", (hash,))
        if not cursor.fetchone(): break

    cursor.execute("INSERT INTO access_tokens (user_id, token_hash, ip, user_agent, created) VALUES (%s, %s, %s, %s, %s)",
    (
        user.id,
        hash,
        request.remote_addr,
        request.headers.get("User-Agent"),
        time.time()
    ))
    database.commit()

    return token, 200

@app.route("/upload_package", methods=["POST"])
def upload_package():
    try: data = get_arguments(ROUTES_ARGUMENTS["upload_package"])
    except InvalidArgument as e: return e.args
    repositoryName = data["repository"]
    packageName = data["name"]
    version = data["version"]

    loggedIn, user = check_login(data["access_token"], fetchUser=True)
    if not loggedIn: return "Invalid Access Token", 401
    
    try: repository = github.get_repo(repositoryName)
    except UnknownObjectException: return "Repository Not Found", 404

    try: repository.get_contents(data["description_file"])
    except UnknownObjectException: return "Description File Not Found", 404

    additionalPackageData = {"user_id": user.id, "latest": True}
    latestRelease = fetch_latest_package_release(packageName)
    if latestRelease:
        if latestRelease.user_id != user.id: return "Insufficient Permissions to Release an Update", 401
        if fetch_package_release(packageName, version): return "Release Already Uploaded", 409

    try: release = repository.get_release(version)
    except UnknownObjectException: return "Release Not Found", 404

    additionalPackageData["release_date"] = release.created_at.timestamp()
    if latestRelease:
        additionalPackageData["latest"] = latestRelease.release_date < additionalPackageData["release_date"]
        if additionalPackageData["latest"]: cursor.execute("UPDATE packages SET latest=false WHERE package_id=%s", (latestRelease.package_id,))

    data.update(additionalPackageData)
    package = Package.parse_obj(data)

    success, reason = package.insert(cursor)
    if not success: return reason

    database.commit()

    return "Package Added", 200

@app.route("/delete_package_version", methods=["POST"])
def delete_package_version():
    try: data = get_arguments(ROUTES_ARGUMENTS["delete_package_version"])
    except InvalidArgument as e: return e.args
    packageName = data["name"]
    version = data["version"]

    loggedIn, user = check_login(data["access_token"], fetchUser=True)
    if not loggedIn: return "Invalid Access Token", 401

    package = fetch_package_release(packageName, version)
    if not package: return f"Package with version \"{version}\" not found", 404
    elif package.user_id != user.id: return "Insufficient Permissions to Delete this Release", 401

    package.delete_release(cursor)

    latestPackage = fetch_latest_package_release(packageName)
    if latestPackage: latestPackage.update(cursor, {"latest": True})
    database.commit()

    return "Package Release Deleted", 200

@app.route("/delete_package", methods=["POST"])
def delete_package():
    try: data = get_arguments(ROUTES_ARGUMENTS["delete_package"])
    except InvalidArgument as e: return e.args
    name = data["name"]

    loggedIn, user = check_login(data["access_token"], fetchUser=True)
    if not loggedIn: return "Invalid Access Token", 401

    package = fetch_latest_package_release(name)
    if not package: return "Package Not Found", 404
    elif package.user_id != user.id: return "Insufficient Permissions to Delete this Package", 401

    package.delete(cursor)
    database.commit()

    return "Package Deleted", 200

@app.route("/get_download", methods=["GET"])
def get_download():
    try: data = get_arguments(ROUTES_ARGUMENTS["get_download"])
    except InvalidArgument as e: return e.args
    name = data["name"]
    version = data["version"] if "version" in data else None

    if version: package = fetch_package_release(name, version)
    else: package = fetch_latest_package_release(name)
    if not package: return "Package Not Found", 404

    success, release = get_github_release(package)
    if not success: return "Package Github Release Not Found", 404
    
    return release.zipball_url, 200

@app.route("/get_package", methods=["GET"])
def get_package():
    try: data = get_arguments(ROUTES_ARGUMENTS["get_package"])
    except InvalidArgument as e: return e.args
    name = data["name"]
    version = data["version"] if "version" in data else None

    if version: package = fetch_package_release(name, version)
    else: package = fetch_latest_package_release(name)
    if not package: return "Package Not Found", 404

    data = package.dict(exclude={"package_id"})
    return jsonify(data), 200

if __name__ == "__main__": app.run("0.0.0.0")