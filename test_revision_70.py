import unittest
from revision_70 import stable_revision
class ModelTests(unittest.TestCase):
    def test_order(self):
        r=stable_revision([100,110,120,130],[90,100,110,120],10,0,{})
        self.assertLess(r['scenarios']['bear'],r['scenarios']['base']);self.assertLess(r['scenarios']['base'],r['scenarios']['bull'])
    def test_missing(self):
        self.assertIsNone(stable_revision([1,2],[1,2],10,0,{}))
    def test_negative(self):
        self.assertIsNone(stable_revision([1,-2,3,4],[1,2,3,4],10,0,{}))
    def test_dilution(self):
        a=stable_revision([100,110,120,130],[90,100,110,120],10,0,{})
        b=stable_revision([100,110,120,130],[90,100,110,120],10,.1,{})
        self.assertLess(b['scenarios']['base'],a['scenarios']['base'])
if __name__=='__main__':unittest.main()
