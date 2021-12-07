# Copyright (c) 2019-2021, Orchestra Culture Co., ltd. All rights reserved.


import sys
import json
import time
import logging
import math
import random
import ssl
import exceptions
import urllib.request
import http.cookiejar
import pytz
import certifi
import urllib3
import os
import re


from datetime import datetime, timedelta, timezone
from collections import OrderedDict
from urllib3._collections import HTTPHeaderDict
from urllib.parse import urlunsplit
from typing import List


from utils import (
    _parse_iso8601_string,
    _md5sum_hash,
    _sha256_hash,
    _hmac_hash,
    _to_signer_date,
    _to_amz_date,
    _generate_headers,
)


__VERSION__ = "0.0.2"


REQUEST_TIMEOUT = 10
POLLING_INTERVAL = 2
CSRF_MIDDLEWARE_TOKEN_NAME = "csrfmiddlewaretoken"
CSRF_TOKEN_NAME = "csrftoken"
X_CSRFTOKEN_NAME = "X-CSRFToken"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0",
    "orchestra-api (%s)" % __VERSION__,
    "Python %s (%s)" % (".".join(
        str(x) for x in sys.version_info[:3]), sys.platform.lower().capitalize()),
    "ssl %s (%s)" % (ssl.OPENSSL_VERSION, "no-validate")
]


__LOG__ = logging.getLogger("orchestra_api3")
__LOG__.setLevel(logging.WARN)


class Api(object):
    def __init__(self, site_url, email=None, password=None, api_key=None, proxy=None, sessionid=None):
        """
        :param site_url: format like http://trial.orchestra-technology.com
        :param email: api user should also login with email.
        :param password: password of human user or client user.
        :param api_key: secret key of api user.
        :param proxy: format like 127.0.0.1:8080.
        :param session_id: with this id, you do not need login again.
        """
        self._async_mode = False
        self._schema = None

        _, host = urllib.parse.splituser(
            urllib.parse.urlsplit(site_url).netloc)
        self.site_url = site_url
        self.domain, self.port = urllib.parse.splitport(host)
        self.email = email
        self.password = password
        self.api_key = api_key
        self.proxy = proxy
        self.sessionid = sessionid

        if self.api_key and not self.password:
            self._credentials = {
                "email": self.email,
                "api_key": self.api_key
            }
        else:
            self._credentials = {
                "email": self.email,
                "password": self.password
            }

        self._s3_credentials = {}

        # TODO: validate input arguments like site_url, email, proxy, etc.
        self.install_opener()
        self.cache_csrftoken()

    def build_opener(self, *handlers):
        _handlers = []
        if self.proxy == "HTTP_PROXY":
            "Do Nothing, urllib.request will get proxy from registry's internet setting section by default."
        elif self.proxy != None:
            proxy_handler = urllib.request.ProxyHandler(
                {"https": self.proxy, "http": self.proxy})
            _handlers.append(proxy_handler)
        else:
            proxy_handler = urllib.request.ProxyHandler()
            _handlers.append(proxy_handler)

        _handlers.extend(handlers)
        return urllib.request.build_opener(*_handlers)

    def install_opener(self):
        cookiejar = http.cookiejar.CookieJar()
        port_spec = True if self.port else False
        cookie = http.cookiejar.Cookie("0", "language", "zh-hans", self.port, port_spec, self.domain, False,
                                       False, "/", True, False, None, False, None, None, {})
        cookiejar.set_cookie(cookie)
        cookie_handler = urllib.request.HTTPCookieProcessor(cookiejar)
        opener = self.build_opener(cookie_handler)
        urllib.request.install_opener(opener)

    def find_cookiejar(self, ):
        global_opener = urllib.request._opener
        handlers = global_opener.handlers
        for handler in handlers:
            if isinstance(handler, urllib.request.HTTPCookieProcessor):
                return handler.cookiejar
        return None

    def get_cached_csrftoken(self, ):
        cookiejar = self.find_cookiejar()
        if cookiejar is not None:
            for item in cookiejar:
                if item.name == CSRF_TOKEN_NAME:
                    return item.value
        return

    def add_x_csrftoken_header(self, request):
        csrftoken = self.get_cached_csrftoken()
        if not csrftoken:
            raise ValueError("csrftoken is empty.")

        request.add_header(X_CSRFTOKEN_NAME, csrftoken)

    def add_general_header(self, request):
        request.add_header("user-agent", "; ".join(USER_AGENTS))
        request.add_header("Accept", "*/*")
        request.add_header("Accept-Encoding", "gzip, deflate")
        request.add_header(
            "Accept-Language", "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2")
        request.add_header("Cache-Control", "no-cache")
        request.add_header("Connection", "keep-alive")
        request.add_header(
            "Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        request.add_header("Content-Length", len(request.data)
                           if request.data else 0)
        request.add_header("Sec-Fetch-Dest", 'empty',)
        request.add_header("Sec-Fetch-Mode", 'cors',)
        request.add_header("Sec-Fetch-Site", "same-origin",)
        request.add_header("X-Requested-With", 'XMLHttpRequest')
        request.add_header("Referer", self.site_url)

    def get_login_url(self):
        return urllib.parse.urljoin(self.site_url, "user/login")

    def get_api_url(self):
        return urllib.parse.urljoin(self.site_url, "crud/requests")

    def get_async_task_url(self):
        return urllib.parse.urljoin(self.site_url, "/queue/task")

    def get_csrf_url(self):
        return urllib.parse.urljoin(self.site_url, "crud/csrftoken")

    def get_schema_url(self):
        return urllib.parse.urljoin(self.site_url, "/page/schema")

    def get_ack_url(self):
        return urllib.parse.urljoin(self.site_url, "/cloud/ack")

    # GET CSRFTOKEN.
    def cache_csrftoken(self):
        request = urllib.request.Request(self.get_csrf_url(), method="GET")
        self.add_general_header(request)

        try:
            response = urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)

        except urllib.error.HTTPError as e:
            __LOG__.debug('HTTPError', e.code, e.read())
            raise e

        except urllib.error.URLError as e:
            __LOG__.debug("URLError", e.reason)
            raise e

        else:
            payload = self.decode_payload(response)
            if "payload" in payload:
                payload = payload["payload"]

            csrftoken = payload[CSRF_TOKEN_NAME]
            path = payload["path"]
            expires = payload["expires"]
            if expires:
                expires = int(time.time()) + int(expires)

            port_spec = True if self.port else False
            cookie = http.cookiejar.Cookie("0", CSRF_TOKEN_NAME, csrftoken, self.port, port_spec, self.domain, False,
                                           False, path, True, False, expires, True, None, None, {})

            cookiejar = self.find_cookiejar()
            if cookiejar is not None:
                __LOG__.debug("Get csrftoken:", cookie.value)
                cookiejar.set_cookie(cookie)

    def login(self):
        """
        LOGIN.
        Cache sessionid in CookieJar.
        """
        content_string = urllib.parse.urlencode(self._credentials)
        content_string = bytes(content_string, encoding='utf8')

        request = urllib.request.Request(
            self.get_login_url(), data=content_string, method="POST")
        self.add_x_csrftoken_header(request)
        self.add_general_header(request)

        try:
            response = urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)

        except urllib.error.HTTPError as e:
            __LOG__.debug('HTTPError', e.code, e.read())
            raise e

        except urllib.error.URLError as e:
            __LOG__.debug("URLError", e.reason)
            raise e

        else:
            # urllib.request will cache sessionid automatically.
            return True

    def set_async_mode(self, async_mode=False):
        """
        All your requests will be treat as background tasks since you set self._async_mode to True.
        """
        self._async_mode = async_mode

    def get_async_mode(self):
        return self._async_mode

    def read_schema(self, refresh=False):
        return self.load_schema(refresh)

    def load_schema(self, refresh=False):
        url = self.get_schema_url()
        if refresh:
            url = urllib.parse.urljoin(self.get_schema_url() + "/", "reload")

        request = urllib.request.Request(url, method="POST")
        self.add_x_csrftoken_header(request)
        self.add_general_header(request)
        response = self._http_request(request)
        self._schema = self.decode_payload(response)
        return self._schema

    def create_entity_type_std(self,
                               name,
                               help="",
                               can_read=False,
                               can_follow=False,
                               can_favor=False,
                               can_publish=False,
                               has_page=True,
                               has_notes=False,
                               has_project=False,
                               has_pipeline=False,
                               has_tags=False,
                               has_pipeline_config_cache=False,
                               has_versions=False,
                               ):
        """
        Async Request.
        Create specified entity type.

        Example:
            api.create(data)

        :param name                     : this argument can contains only letters and numbers.
        :param help                     : option
        :param can_read                 : option
        :param can_follow               : option
        :param can_favor                : option
        :param can_publish              : option
        :param has_page                 : option
        :param has_notes                : option
        :param has_project              : option
        :param has_pipeline             : option
        :param has_tags                 : option
        :param has_pipeline_config_cache: option
        :param has_versions             : option
        :returns                        : async task id.
        """
        entity_type = 'EntityType'
        data = [{
            "name": name,
            "help": help,
            "can_read": can_read,
            "can_follow": can_follow,
            "can_favor": can_favor,
            "can_publish": can_publish,
            "has_page": has_page,
            "has_notes": has_notes,
            "has_project": has_project,
            "has_pipeline": has_pipeline,
            "has_pipeline_config_cache": has_pipeline_config_cache,
            "has_tags": has_tags,
            "has_versions": has_versions,
        }]
        self.set_async_mode(True)
        task_id = self.create(entity_type, data)
        self.set_async_mode(False)
        return task_id

    def _request_schema(self, request_type, entity_type, data: List[dict]):
        assert isinstance(data, list), "data should be list."
        assert data, "data should not be empty."
        assert entity_type in [
            "EntityType", "Field"], "_request_schema only receive two types of entity_type: 'EntityType', 'Field'."

        method = getattr(self, request_type)
        assert method, "Invalid request type: " + request_type

        self.set_async_mode(True)
        task_id = method(entity_type, data)
        self.set_async_mode(False)
        return task_id

    def create_entity_type(self, data: List[dict]):
        """
        Async Request.
        Create specified entity type.

        Example:
            api.create_entity_type(
                [{"name": "NewEntity", "help": "description"}])

        :param data : new entity type data.
        :returns    : async task id.
        """
        assert all(["name" in d for d in data]
                   ), "item in data should has 'name' attribute."
        return self._request_schema("create", "EntityType", data)

    def update_entity_type(self, data: List[dict]):
        """
        Async Request.
        Update specified entity type.

        Example:
            api.update_entity_type(
                [{"name": "NewEntity", "help": "test update description"}])

        :param data : new entity type data.
        :returns    : async task id.
        """
        assert all(["id" in d or "name" in d for d in data]
                   ), "item in data should has 'id' or 'name' attribute."
        return self._request_schema("update", "EntityType", data)

    def delete_entity_type(self, data: List[dict]):
        """
        Async Request.
        Update specified entity type.

        Example:
            api.delete_entity_type([{'id': 1053}])

        :param data : [{'id': 1053}].
        :returns    : async task id, solved result looks like [{'id': 1053}].
        """
        assert all(["id" in d for d in data]
                   ), "item in data should has 'id' attribute."
        return self._request_schema("delete", "EntityType", data)

    def create_field(self, data: List[dict]):
        """
        Async Request.
        Create specified field.

        Example:
            api.create_field(
                [{"entity_type": "Task", "name": "text", "data_type": "text"}])

        :param data : must contain 'entity_type', 'name' and 'data_type'.
        :returns    : async task id.
        """
        assert all(["entity_type" in d and "name" in d and "data_type" in d for d in data]
                   ), "item in data should has 'entity_type', 'name' and 'data_type."
        return self._request_schema("create", "Field", data)

    def update_field(self, data: List[dict]):
        """
        Async Request.
        Update specified field.

        Example:
            api.update_field(
                [{"entity_type": "Task", "name": "text", "help": "test modify help attribute."}])

        :param data : must contain 'entity_type' and 'name' to ensure field location in table.
        :returns    : async task id.
        """
        assert all([("entity_type" in d and "name" in d) or "id" in d for d in data]
                   ), "item in data should has either 'entity_type' & 'name' or 'id."
        return self._request_schema("update", "Field", data)

    def delete_field(self, data: List[dict]):
        """
        Async Request.
        Delete specified field.

        Example:
            api.delete_field([{"id": 1537}])

        :param data : new field data must contain 'id' to ensure field location in table.
        :returns    : async task id.
        """
        assert all(["id" in d for d in data]), "item in data should has 'id'."
        return self._request_schema("delete", "Field", data)

    def read(self, entity_type, fields=[], filters={}, sorts=[], groups=[], pages={}, additional_filters=None):
        """
        Read entities by specified rules.

        Example:
            api.read("Task",
                fields=[["id", "name", "status"]],
                filters=["project", "is", {"id": 1, "type": "Project"}],
                sorts=[{ "column": "name", "direction": "ASC" }],
                groups=[
                    {
                        "column": "entity",
                        "method": "exact",
                        "direction": "asc",
                    },
                ],
                pages={"page": 1, "page_size": 5}
            )

        Checks in examples.py to find more examples.

        :param request_type         : 'read'
        :param entity_type          : type of entity you will read.
        :param columns              : returned entities will have this fields.
        :param filters              : specify filter condition here.
        :param sorts                : specify sort mode here.
        :param groups               : specify group mode here.
        :param pages                : specify page mode here, for example: {"page": 1, "page_size": 5} is just perfect.
        :param additional_filters   : support RecycleFilter in backend, pass '{"recycle": {"method": "exclude"}}' to get alive entity,
                                      '{"recycle": {"method": "include"}}' to get retired entity.
        :param local_timezone_offset: ignore
        :param append               : ignore
        :param storeId              : ignore
        :returns                    : will be dict if page_size equals to 1 else list.
        """
        requests = self.build_read_payload(
            entity_type, fields, filters, sorts, groups, pages, additional_filters)
        try:
            data = self._send_request(requests)
        except:
            raise
        else:
            return data

    def create(self, entity_type, data: List[dict]):
        """
        Create specified entities.

        Example:
            api.create(entity_type, data)

        :param request_type         : 'create'
        :param entity_type          : type of entity you will create.
        :param columns              : ignore
        :param data                 : pass data like '[{"name": "new entity", "status": "wtg"}]'
        :param local_timezone_offset: ignore
        :param storeId              : ignore
        """
        payload = self.build_payload('create', entity_type, None, data)
        try:
            data = self._send_request(payload)
        except:
            raise
        else:
            return data

    def update(self, entity_type, data: List[dict]):
        """
        Update specified entities.

        Example:
            api.update("Task", data=[{"name":"Layout Modified","id":1}])

        Checks in examples.py to find more examples.

        :param request_type         : 'update'
        :param entity_type          : type of entity you will update.
        :param columns              : ignore
        :param data                 : []
        :param local_timezone_offset: ignore
        :param storeId              : ignore
        """
        payload = self.build_payload('update', entity_type, None, data)
        try:
            data = self._send_request(payload)
        except:
            raise
        else:
            return data

    def delete(self, entity_type, data):
        """
        Delete specified entities.

        Example:
            api.delete(entity_type, data)

        :param request_type         : 'delete'
        :param entity_type          : type of entity you will delete.
        :param columns              : ignore
        :param data                 : pass data like '[{"id": 1}, {"id": 2}]'.
        :param local_timezone_offset: ignore
        :param storeId              : ignore
        """
        payload = self.build_payload('delete', entity_type, None, data)
        try:
            data = self._send_request(payload)
        except:
            raise
        else:
            return data

    def duplicate(self, entity_type, fields, data):
        """
        TODO: Duplicate specified entities.

        Example:
            api.duplicate(entity_type, fields, data)

        :param request_type         : 'duplicate'
        :param entity_type          : type of entity you will duplicate.
        :param columns              : you can specify which fields will be duplicated, or pass a empty list to duplicate all fields.
        :param data                 : pass data like '[{"id": 1}, {"id": 2}]'.
        :param sorts                : ignore
        :param grouping             : ignore
        :param local_timezone_offset: ignore
        :param append               : ignore
        :param storeId              : ignore
        """
        return

    def resolve_async_task(self, task_id):
        """
        Resolve task result from server.

        Example:
            api.resolve_async_task(task_id)

        :param task_id: task id returned by server.

        :returns: raise exceptions.RequestFailed if async task is not finished.
        """
        data = {"task_id": task_id}
        request = self._build_async_task_request(data)
        response = self._http_request(request)
        return self._process_async_task_response(response)

    def polling_async_task(self, task_id):
        """
        Polling task result from server until it finished.

        Example:
            api.resolve_async_task(task_id)

        :param task_id: task id returned by server.

        :returns: async task result.
        """
        data = {"task_id": task_id}
        request = self._build_async_task_request(data)
        response = self._polling_http_request(request)
        return self._process_async_task_response(response)

    def build_payload(self, request_type, entity_type, fields, data):
        payload = {
            "request_type": request_type,
            "entity_type": entity_type,
        }
        if fields:
            payload["columns"] = fields
        if data:
            payload["data"] = data

        return [payload]

    def build_read_payload(self,
                           entity_type,
                           fields,
                           filters,
                           sorts,
                           groups,
                           pages,
                           additional_filters):
        payload = {
            "request_type": "read",
            "entity_type": entity_type,
        }
        if fields:
            payload["columns"] = fields
        if filters:
            payload["filters"] = self.process_filters(filters)
        if sorts:
            payload["sorts"] = sorts
        if groups:
            payload["grouping"] = groups

        payload["paging"] = self.get_pages(pages)

        if additional_filters:
            payload["filter_setting"] = additional_filters

        return [payload]

    def get_request_id(self):
        return math.floor(random.random() * time.time())

    def get_relations(self):
        return ["is", "is_not", "less_than", "greater_than", "contains", "excludes", "in", "starts_with", "ends_with"]

    def process_filters(self, filters: list):
        """
        Convert list to dict which server can recognize.

        :param filters: simple writing.

        Example 1: convert ["name", "is", "Layout"] to
        {
            "operator": "and",
            "conditions": [
                {
                    "path": "name",
                    "relation": "is",
                    "values": "Layout"
                },
            ]
        }

        Example 2: convert [["name", "is", "Layout"], ["status", "is", "wtg"]] to
        {
            "operator": "and",
            "conditions": [
                {
                    "path": "name",
                    "relation": "is",
                    "values": Layout
                },
                {
                    "path": "status",
                    "relation": "is",
                    "values": "wtg"
                },
            ]
        }

        Example 3: convert ["or", ["name", "is", "Layout"], ["status", "is", "wtg"]] to
        {
            "operator": "or",
            "conditions": [
                {
                    "path": "name",
                    "relation": "is",
                    "values": Layout
                },
                {
                    "path": "status",
                    "relation": "is",
                    "values": "wtg"
                },
            ]
        }

        You can construct event more complex filter condition with above usages.
        """
        # record which floor we iterated to.
        inject = 0
        fallback_filters = filters

        # ensure operator.
        operator = filters[0]
        if operator in ["or", "and"]:
            filters = filters[1:]
        else:
            operator = "and"

        # recognize injected filters.
        if all(map(lambda f: isinstance(f, list), filters)):
            inject += 1
            union = {"operator": operator}
            conditions = []
            for flt in filters:
                result = self.process_filters(flt)

                # TODO: add result to conditions
                conditions.append(result)
            union["conditions"] = conditions
            return union
        else:
            # maybe operator name is equal to field name.
            filters = fallback_filters

        # Valid length.
        assert len(
            filters) == 3, "%s does not conform [field, relation, values]." % filters
        # Valid field, relation.
        assert filters[1], "%s is not valid." % filters[1]

        condition = {
            "path": filters[0],
            "relation": filters[1],
            "values": filters[2] if isinstance(filters[2], list) else [filters[2]]
        }

        # process ['name', 'is', 'Layout'] instead of [['name', 'is', 'Layout']].
        if inject == 0:
            condition = {
                "operator": operator,
                "conditions": [condition]
            }
        return condition

    def get_pages(self, pages):
        """
        Server will determine 'pages' if it is absence.
        maximum page_size is 200, minimnum is 50.
        """
        return pages

    def process_payload(self, requests):
        requests_encoded = json.dumps(requests)
        async_mode = json.dumps(self.get_async_mode())

        return {
            "requestId": self.get_request_id(),
            "requests": requests_encoded,
            "async": async_mode,
        }

    def encode_payload(self, payload):
        payload_encoded = urllib.parse.urlencode(payload)
        return bytes(payload_encoded, encoding='utf-8')

    def decode_payload(self, response):
        string = response.read()
        return json.loads(string.decode())

    def get_rows(self, payload):
        """
        :returns: list type, or dict if page_size equals to 1.
        """
        rows = payload.get("rows")
        pages = payload.get("paging", {})
        page_size = pages.get("page_size", None)
        if page_size == 1 and rows:
            return rows[0]
        return rows

    def group_by(self, payload: dict):
        grouped_rows = []
        rows = self.get_rows(payload)
        groups = payload.get("groups")
        for group in groups:
            ids = group.get("ids")
            display_name = group.get("display_name")
            new_group = {"display_name": display_name, "children": []}
            for id in ids:
                for row in rows:
                    if row.get("id") == id:
                        new_group["children"].append(row)
                        break
            grouped_rows.append(new_group)
        return grouped_rows

    def _build_async_task_request(self, payload: dict):
        payload_string = json.dumps(payload)
        payload_encoded = bytes(payload_string, encoding='utf-8')

        request = urllib.request.Request(
            self.get_async_task_url(), data=payload_encoded, method="POST")
        self.add_x_csrftoken_header(request)
        self.add_general_header(request)

        return request

    def _build_crud_request(self, payload):
        payload = self.process_payload(payload)
        payload_encoded = self.encode_payload(payload)

        request = urllib.request.Request(
            self.get_api_url(), data=payload_encoded, method="POST")
        self.add_x_csrftoken_header(request)
        self.add_general_header(request)

        return request

    def _http_request(self, request: urllib.request.Request):
        try:
            return urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)

        except urllib.error.HTTPError as e:
            return self._process_http_error(e)

        except urllib.error.URLError as e:
            __LOG__.debug('URLError', e.reason)
            raise e

    def _polling_http_request(self, request: urllib.request.Request):
        response = None

        def _is_async_task_running(request):
            nonlocal response
            response = self._http_request(request)
            __LOG__.debug("Polling...")
            return response.status == 202

        while _is_async_task_running(request):
            time.sleep(POLLING_INTERVAL)

        return response

    def _send_request(self, payload: List[dict]):
        request = self._build_crud_request(payload)
        response = self._http_request(request)
        return self._process_response(response)

    def _process_request(self):
        """
        TODO
        """
        return

    def _process_response(self, response):
        """
        TODO: lock async_mode in period between request and response.
        """
        payload = self.decode_payload(response)

        if self.get_async_mode():
            return self._processs_async_payload(payload)

        return self._extract_payload(payload)

    def _process_async_task_response(self, response):
        payload = self.decode_payload(response)
        if not payload["success"]:
            msg = payload.get('message')
            raise exceptions.RequestFailed(
                "Request Failed: " + self._extract_message(msg))

        task_payload = payload["data"]
        return self._extract_payload(task_payload)

    def _extract_payload(self, payload):
        # hard code
        # actually we should extract every items in payload.
        payload = payload[0]

        if payload:
            if payload["success"]:
                if payload.get("groups"):
                    return self.group_by(payload)
                return self.get_rows(payload)
            else:
                msg = payload.get('message')
                raise exceptions.RequestFailed(
                    "Request Failed: " + self._extract_message(msg))
        raise exceptions.UnknownError(
            "Should has failed detail but payload is empty.")

    def _processs_async_payload(self, payload):
        if payload["success"]:
            return payload["task_id"]
        msg = payload.get('message')
        raise exceptions.RequestFailed(
            "Request Failed: " + self._extract_message(msg))

    def _process_http_error(self, http_error):
        """
        TODO
        """
        payload = self.decode_payload(http_error)
        __LOG__.debug('HTTPError', payload)

        if isinstance(payload, list):
            payload = payload[0]

        if payload:
            if payload.get("success"):
                raise exceptions.UnknownError(
                    "This request should be failed, maybe server get confused.")
            else:
                raise exceptions.RequestFailed(
                    "ERROR: " + payload.get("message", {}).get("detail"))
        raise exceptions.UnknownError(
            "Should has failed detail but payload is empty.")

    def _extract_message(self, message):
        if isinstance(message, str):
            return message
        elif isinstance(message, dict) and "detail" in message:
            return message.get("detail") or ""
        else:
            return json.dumps(message)

    def upload_attachment(self, path, url=None, project=None, entity=None):
        """
        Upload attachment to orchestra oss and create attachment entity to record oss url, 
        then create entity linked to attachment.

        :param path   : file path.
        :param url    : url behind bucket name, it can be relative path like 'project/sequence/shot/task/version/mov/sample.mov'.
        :param entity : link to generated attachment: {'id': 1, 'type': 'Version'}.
        :returns      : async task id.
        """
        try:
            self.enable_s3()
            self._s3_upload(url, path)
        except:
            raise

        original_fname = os.path.basename(path)
        filename = os.path.basename(url)
        display_name, _ = os.path.splitext(filename)
        _, file_extension = os.path.splitext(path)
        file_extension = file_extension.lower()
        file_size = os.stat(path).st_size

        attachments = self.create("Attachment", data=[{
            'this_file': url,
            'filename': filename,
            'display_name': display_name,
            'original_fname': original_fname,
            'file_extension': file_extension,
            'file_size': file_size,
            'thumbnail': '',  # TODO
            'status': "act",
            'project': project,
            'attachment_type': "cloud"}])
        attachment = attachments[0]
        attachment["type"] = "Attachment"
        if entity:
            self.create("AttachmentLink", data=[{
                'attachment': attachment,
                'entity': entity}])
        return attachment

    def enable_s3(self):
        if self._is_s3_expired():
            self._get_s3_security_token()

    def _get_s3_security_token(self):
        """[summary]

        :returns    : credential dictionary.
        """
        request = urllib.request.Request(
            self.get_ack_url(), method="POST")
        self.add_x_csrftoken_header(request)
        self.add_general_header(request)

        response = self._http_request(request)
        payload = self.decode_payload(response)
        self._setup_s3_client(payload)
        return payload

    def _setup_s3_client(self, data):
        self._s3_credentials["EndPoint"] = data["EndPoint"]
        self._s3_credentials["Secure"] = data["Secure"]
        self._s3_credentials["Bucket"] = data["Bucket"]
        self._s3_credentials["Region"] = data["Region"]
        self._s3_credentials["AccessKeyId"] = data["ack"]["AccessKeyId"]
        self._s3_credentials["SecretAccessKey"] = data["ack"]["SecretAccessKey"]
        self._s3_credentials["SessionToken"] = data["ack"]["SessionToken"]
        # utc time.
        self._s3_credentials["Expiration"] = data["ack"]["Expiration"]

        timeout = timedelta(minutes=1).seconds
        self._s3_client = urllib3.PoolManager(
            timeout=urllib3.util.Timeout(connect=timeout, read=timeout),
            maxsize=10,
            cert_reqs='CERT_REQUIRED',
            ca_certs=os.environ.get('SSL_CERT_FILE') or certifi.where(),
            retries=urllib3.Retry(
                total=5,
                backoff_factor=0.2,
                status_forcelist=[500, 502, 503, 504]
            )
        )

    def _is_s3_expired(self):
        expiration = self._s3_credentials.get("Expiration")
        if not expiration:
            return True
        dt_expiration = _parse_iso8601_string(expiration)
        return dt_expiration < datetime.now(pytz.utc)

    def _s3_upload(self, object_name, path):
        with open(path, "rb") as file_object:
            return self._s3_request("PUT", object_name, file_object, preload_content=True)

    def _s3_download(self, object_name, path):
        with open(path, "ab") as file_object:
            response = self._s3_request(
                "GET", object_name, preload_content=False)
            for data in response.stream(amt=1024*1024):
                file_object.write(data)

            if response:
                response.close()
                response.release_conn()

    def _s3_request(self, method, object_name, file_object=None, preload_content=True):
        service_name = "s3"
        end_point = self._s3_credentials["EndPoint"]
        region = self._s3_credentials["Region"]
        bucket = self._s3_credentials["Bucket"]
        access_key = self._s3_credentials["AccessKeyId"]
        secret_key = self._s3_credentials["SecretAccessKey"]

        url = urllib.parse.SplitResult(
            "https" if self._s3_credentials["Secure"] else "http",
            end_point,
            f'/{bucket}/{object_name}',
            '',
            ''
        )

        """Build headers with given parameters."""
        headers = _generate_headers(None, None, None, None, False)
        headers["Content-Type"] = "application/octet-stream"
        md5sum_added = headers.get("Content-MD5")
        headers["Host"] = url.netloc
        headers["User-Agent"] = "; ".join(USER_AGENTS)
        sha256 = None
        md5sum = None

        body = file_object.read() if file_object else None

        if body:
            headers["Content-Length"] = str(len(body))

        md5sum = None if md5sum_added else _md5sum_hash(body)
        if md5sum:
            headers["Content-MD5"] = md5sum

        sha256 = "UNSIGNED-PAYLOAD"
        headers["x-amz-content-sha256"] = sha256
        headers["X-Amz-Security-Token"] = self._s3_credentials["SessionToken"]
        date = datetime.utcnow().replace(tzinfo=timezone.utc)
        headers["x-amz-date"] = _to_amz_date(date)

        """Do signature V4 of given request for given service name."""
        scope = f"{_to_signer_date(date)}/{region}/{service_name}/aws4_request"

        """Get canonical headers."""
        canonical_headers = {}
        for key, values in headers.items():
            key = key.lower()
            if key not in (
                    "authorization", "content-type",
                    "content-length", "user-agent",
            ):
                values = values if isinstance(
                    values, (list, tuple)) else [values]
                canonical_headers[key] = ",".join([
                    re.compile(r"( +)").sub(" ", value) for value in values
                ])

        canonical_headers = OrderedDict(sorted(canonical_headers.items()))
        signed_headers = ";".join(canonical_headers.keys())
        canonical_headers = "\n".join(
            [f"{key}:{value}" for key, value in canonical_headers.items()],
        )
        canonical_query_string = ""
        content_sha256 = sha256
        canonical_request = (
            f"{method}\n"
            f"{url.path}\n"
            f"{canonical_query_string}\n"
            f"{canonical_headers}\n\n"
            f"{signed_headers}\n"
            f"{content_sha256}"
        )

        canonical_request_hash = _sha256_hash(canonical_request)

        string_to_sign = (
            f"AWS4-HMAC-SHA256\n{_to_amz_date(date)}\n{scope}\n"
            f"{canonical_request_hash}"
        )

        """Get signing key."""
        date_key = _hmac_hash(
            ("AWS4" + secret_key).encode(),
            _to_signer_date(date).encode(),
        )
        date_region_key = _hmac_hash(date_key, region.encode())
        date_region_service_key = _hmac_hash(
            date_region_key, service_name.encode(),
        )
        signing_key = _hmac_hash(date_region_service_key, b"aws4_request")

        """Get signature."""
        signature = _hmac_hash(
            signing_key, string_to_sign.encode(), hexdigest=True)

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        headers["Authorization"] = authorization

        http_headers = HTTPHeaderDict()
        for key, value in (headers or {}).items():
            if isinstance(value, (list, tuple)):
                _ = [http_headers.add(key, val) for val in value]
            else:
                http_headers.add(key, value)

        return self._s3_client.urlopen(
            method,
            urlunsplit(url),
            body=body,
            headers=http_headers,
            preload_content=preload_content,
        )
