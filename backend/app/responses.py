from flask import g, jsonify


def success(data, status=200):
    return jsonify(ok=True, data=data, requestId=g.request_id), status


def failure(code, message, status):
    return jsonify(
        ok=False, error={"code": code, "message": message}, requestId=g.request_id
    ), status
