# -*- coding: utf-8 -*-
"""
Created on Tue Apr 26 11:14:47 2016

@author: rwb27

Example:

>>>

"""

import nplab.utils.notified_property import NotifiedProperty, DumbNotifiedProperty

def a_changed(a):
    print "a is now {0}".format(a)
    
def b_changed(a):
    print "b is now {0}".format(a)
    
def c_changed(a):
    print "c is now {0}".format(a)
    
class foo():
    a = DumbNotifiedProperty()
    b = DumbNotifiedProperty(10)
    @NotifiedProperty
    def c(self):
        return 99
    @c.setter
    def c(self, val):
        print "discarding {0}".format(val)
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()
