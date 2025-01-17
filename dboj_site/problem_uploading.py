import zipfile
import os
import yaml
from google.cloud import storage

max_size = 512 # Maximum memory limit for languages

def delete_blob(storage_client, blobname):
    blob = storage_client.blob(blobname)
    blob.delete()
    
def upload_blob(storage_client, sourceName, blobname):
    bucket = storage_client.bucket('discord-bot-oj-file-storage')
    blob = bucket.blob(blobname)
    blob.upload_from_filename(sourceName)

def uploadProblem(settings, storage_client, author):
    with zipfile.ZipFile("data.zip", 'r') as zip_ref:
        zip_ref.extractall("problemdata")
    
    try:
        params = yaml.safe_load(open("problemdata/params.yaml", "r"))
        existingProblem = settings.find_one({"type":"problem", "name":params['name']})

        if not existingProblem is None:
            if (not author in existingProblem['authors']):
                raise Exception("Error: problem name `" + params["name"] + "` already exists under another author")
            settings.delete_one({"_id":existingProblem['_id']})

        contest = ""
        try:
            contest = params['contest']
        except:
            pass

        if contest is None:
            contest = ""
        
        authors = params['authors']
        if not author in authors:
            authors.append(author)

        settings.insert_one({"type":"problem", "name":params['name'], "authors":authors, "points":params['difficulty'], "status":"s", "types":(params.get('types') if not params.get('types') is None else []), "published":params['private'] == 0, "contest":contest})

        batches = params['batches']
        for x in range(1, len(batches) + 1):
            for y in range(1, batches[x - 1] + 1):
                data_file_name = "data" + str(x) + "." + str(y)
                upload_blob(storage_client, "problemdata/" + data_file_name + ".in", "TestData/" + params['name'] + "/" + data_file_name + ".in")

                try:
                    upload_blob(storage_client, "problemdata/" + data_file_name + ".out", "TestData/" + params['name'] + "/" + data_file_name + ".out")
                except:
                    pass
        
        try:
            cases = open("problemdata/cases.txt", "w")
            for x in batches:
                cases.write(str(x) + " ")
            cases.write("\n")
            for x in params['points']:
                cases.write(str(x) + " ")
            cases.write("\n")
            cases.flush()
            cases.close()
            upload_blob(storage_client, "problemdata/cases.txt", "TestData/" + params['name'] + "/cases.txt")
        except Exception as e:
            print(str(e))
            raise Exception("Error with uploading cases")

        d = {}
        d['time-limit'] = params['time-limit']
        d['memory-limit'] = params['memory-limit']

        for x in d['memory-limit']:
            if d['memory-limit'][x] > max_size * 1024:
                raise Exception("Memory limit for " + x + " is too high. The maximum is " + str(max_size) + " MB.")

        yaml.safe_dump(d, open("problemdata/resources.yaml", "w"))
        upload_blob(storage_client, "problemdata/resources.yaml", "TestData/" + params['name'] + "/resources.yaml")

        upload_blob(storage_client, "problemdata/description.md", "ProblemStatements/" + params['name'] + ".txt")
        
        try:
            upload_blob(storage_client, "problemdata/checker.py", "TestData/" + params['name'] + "/checker.py")
        except:
            pass
    except KeyError as e:
        raise Exception("The parameter " + str(e) + " is missing from the params.yaml file")
    
    return ("Successfully uploaded problem data as problem \"" + params['name'] + "\"!")