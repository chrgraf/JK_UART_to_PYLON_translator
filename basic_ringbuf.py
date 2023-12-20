#!/usr/bin/python3
# basic script derived from: https://www.saltycrane.com/blog/2007/11/python-circular-buffer/


class myRingBuffer:
    def __init__(self, size):
        self.data = [None] * size

    def append(self, x):
        self.data.pop(0)
        self.data.append(x)

    def get(self):
        return self.data
    
    def full(self):
       # provides true only if all elemts are different from default None
       for x in self.data:
          if (x==None):
             return(False)
       return(True)
    
    def empty(self):
       # provides true only if all elemts are uninitialized
       for x in self.data:
          if (x!=None):
             return(False)
       return(True)
  
  
    def min(self):
       # provides false in case array is fully empty
       # if at least one elelent got added, then this would be reported as min
       for x in self.data:
          if (x!=None):
             min=x
             break
          else:
             min=False
       for x in self.data:
          if (x!=None and x<min):
             min=x
       return(min)
        
    def max(self):
       # provides false in case array is fully empty
       # if at least one elelent got added, then this would be reported as max
       for x in self.data:
          if (x!=None):
             max=x
             break
          else:
             max=False
       for x in self.data:
          if (x!=None and x>max):
             max=x
       return(max)
           
    def test():
       buf = myRingBuffer(4)
       print(buf.get())
       print("min :", buf.min())
       print("max :", buf.max())
       for i in range(10):
         buf.append(i)
         print(buf.get())
         print(buf.full())
         print("min :", buf.min())
         print("max :", buf.max())



