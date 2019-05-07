## Hydrus Network (mysql port)
This is an experimental port of Hydrus Network from it's own sqlite databases to mysql. Also, I tried to remove all limitations (mostly network and threading ones) I've encountered.

Installation:
* Tested on Windows 7
* Install mysql 8 (not tested on mariadb) and it's bundled python connector (pure python connector is too slow)
* Install requirements from the Pipfile system-wide (you may need to correct the links)
* Create user (not the db) in mysql
* Rename config.example.yaml to config.yaml and correct it as needed. json_path is folder where large json blobs are stored and should be backed up with the db.
* Copy ffmpeg.exe to bin directory.
* Run python client.py.

Not tested:
* Server is not ported yet and should be broken for now.
* Similar file search.
* Client API
* Migration from existing sqlite db is possible (I did it myself), but easy migration scripts are not yet written.
* Multiple clients conections to single DB should not work.
