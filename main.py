#!/usr/bin/env python
from kindle import booktoForum
from cleanup import Cleanup
from iapps import apptoForum
from time import sleep

if __name__ == "__main__":
    ct = 0
    while True:
        apptoForum.run()
        print("App runs:", ct, "times")
        if ct == 6:
            Cleanup.books()
            booktoForum.run()
            ct = 0
        else:
            ct += 1
        sleep(3600)
        Cleanup.udemy()
        # booktoForum.run()
        # sleep(10)
        # print("Sleeping 10s")
