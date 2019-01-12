#!/bin/bash

/hydrus/client.py &
wait

export QT_X11_NO_MITSHM=1
/hydrus/client.py