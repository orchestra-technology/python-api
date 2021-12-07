from api import Api


base_url = "https://trial.orchestra-technology.com"


"""
Example for login method.
"""
client = Api(base_url, "test@orchestra-technology.com", "test@123")
client.login()


"""
Example for login with api user.
"""
client = Api(base_url, "api_user@orchestra-technology.com", api_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
client.login()


"""
Example for read schema method.
"""
schema = client.read_schema()


"""
Example for create entity type method.
entity type name can contains only letters and numbers.
"""
task_id = client.create_entity_type_std("EntityTypeA")


"""
Example for create entity type method.
entity type name can contains only letters and numbers.
"""
task_id = client.create_entity_type([{"name": "EntityTypeA", "help": "My new entity."}])


"""
Example for update entity type method.
"""
task_id = client.update_entity_type([{"name": "EntityTypeA", "help": "test update description"}])


"""
Example for delete entity type method.
"""
task_id = client.delete_entity_type([{'id': 1053}])


"""
Example for create field method.
"""
task_id = client.create_field([{"entity_type": "Task", "name": "text", "data_type": "text"}])


"""
Example for update field method.
"""
task_id = client.update_field([{"entity_type": "Task", "name": "text", "help": "test modify help attribute."}])


"""
Example for delete field method.
"""
result = client.read("Field", ['id', 'name'], [['name', 'is', 'text'], ['entity_type__name', 'is', 'Task']], pages={"page":1, "page_size":1})
field_id = result.get("id")
task_id = client.delete_field([{"id": field_id}])


"""
Example for create method.
"""
client.create("Task", data=[{"name": "New Layout", "project": {"id": 1, "type": "Project"}, "entity": {"id": 1, "type": "Shot"}}])


"""
Example for read method.
"""
# EXAMPLE: READ() with single entity type.
client.read("Task")


# EXAMPLE: read() with fields.
client.read("Task", fields=["id", "name", "status", "entity"])


# EXAMPLE: read() with filters.
client.read("Task", filters=["name", "is", "Layout"])


# EXAMPLE: read() with 'and' filters by default.
client.read("Task", filters=[["name", "is", "Layout"], ["project", "is", {"id": 2, "type": "Project"}]])


# EXAMPLE: read() with 'or' filters.
client.read("Task", filters=["or", ["name", "is", "Layout"], ["project", "is", {"id": 2, "type": "Project"}]])


# EXAMPLE: read() with complex filters.
client.read("Task", filters=[["or", ["name", "is", "Layout"], ["project", "is", {"id": 2, "type": "Project"}]], ["status", "is", "wtg"]])


# EXAMPLE: read() with single sorts.
client.read("Task", fields=["id", "name"], sorts=[{ "column": "name", "direction": "ASC" }])


# EXAMPLE: read() with multiple types of sorts.
client.read("Task", fields=["id", "name", "status"], sorts=[{ "column": "name", "direction": "ASC" }, { "column": "status", "direction": "DESC" }])


# EXAMPLE: read() with groups.
client.read("Task", fields=["id", "name"], groups=[{"column": "name", "method": "exact", "direction": "asc"}])


# EXAMPLE: read() with pages.
client.read("Task", fields=["id", "name"], pages={"page": 1, "page_size": 5})


# EXAMPLE: read() with pages.
client.read("Task", fields=["id", "name"], pages={"page": 2, "page_size": 5})


# EXAMPLE: read() with all of arguments.
client.read("Task", 
    fields=[["id", "name", "version"]], 
    filters=["project", "is", {"id": 1, "type": "Project"}],
    sorts=[{ "column": "name", "direction": "ASC" }],
    groups=[
        {
            "column": "entity",
            "method": "exact",
            "direction": "asc",
        },
    ],
    pages={"page": 1, "page_size": 25}
)


"""
Example for update method.
"""
client.update("Task", data=[{"name": "Layout", "id": 1}])


"""
Example for delete method.
NOTE: given id comes from 'create' example.
"""
client.delete("Task", data=[{"id": 37}])


"""
Example for async request.
"""
client.set_async_mode(True)
task_id = client.update("Task", data=[{"name": "Layout","id": 1}])
client.set_async_mode(False)

# Get result of async task from server.
# Raise exception is task is failed.
try:
    client.polling_async_task(task_id)
except:
    raise


"""
Example for create a attachment while uploading a file.
"""
client.upload_attachment("C:/sample.jpg", "upload/sample.jpg" )


"""
Example for upload file.
"""
client.enable_s3()
# client._s3_credentials["EndPoint"] = "DevelopmentEndPoint"
# client._s3_credentials["Secure"] = False
client._s3_upload("upload/sample.jpg", "C:/sample.jpg")


"""
Example for download file.
"""
client.enable_s3()
client._s3_download("upload/sample.jpg", "C:/sample_download.jpg")