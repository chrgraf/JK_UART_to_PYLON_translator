#!/usr/bin/python3
# basic script derived from: https://www.saltycrane.com/blog/2007/11/python-circular-buffer/


class myRingBuffer:
    def __init__(self, size):
        self.data = [None] * size
    
    def flush(self):
        len=self.len()
        self.data = [None] * len

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
 
 
    def average(self):
       # first determine provides amount of non empty elements
       total_elements=0
       non_empty_count = 0 
       empty_count = 0 
       sum = 0 
       for x in self.data:
          total_elements= total_elements +1
          if (x!=None):
             non_empty_count = non_empty_count +1
             sum = sum + x
          else:
             empty_count= empty_count +1
       if non_empty_count == 0:
          average=0
       else:
          average=sum/non_empty_count
       return (average)

    def min(self):
       # provides false in case array is fully empty
       # if at least one element got added, then this would be reported as min
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

    def len(self):
       len=0
       for x in self.data:
          len = len +1
       return(len)
    
    def lt_count(self,value):
       result=0
       for x in self.data:
          if (x!=None):
             if (x<value):
                result=result+1
       return(result)

    def gt_count(self,value):
       result=0
       for x in self.data:
          if (x!=None):
             if (x>value):
                result=result+1
       return(result)

           


def main():
       buf = myRingBuffer(4)
       print(buf.get())
       print("min :", buf.min())
       print("max :", buf.max())
       for i in range(10):
         print("------ new run #",i)
         buf.append(i)
         print("content of the ringbuffer:",buf.get())
         print("Ringbuffer full          :", buf.full())
         print("min                      :", buf.min())
         print("max                      :", buf.max())
         print("elements larger 7        :",buf.gt_count(7))
       print("<<<< loop done >>>>")
       # flush
       print("Flushing it")
       buf.flush()
       print("content after flush      :",buf.get())
       print("Ringbuffer full          :", buf.full())


if __name__ == "__main__":
    main()


