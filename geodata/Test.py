#from geodata import Geodata, DB
import importlib
import inspect
import os
import re

def pred(ob):
    return inspect.ismethod(ob) or inspect.isclass(ob) or inspect.isfunction(ob)

def display_modules(cls):
    print(f'-------{cls}---------')
    for item in inspect.getmembers(cls, inspect.isfunction):
        module = item[1]
        if item[0][0] != '_':
            print(f'{item[0]}\n' )
            print(f'{module.__doc__}\n' )
            
base_dir = '/Users/mikeherbert/Documents/'  
            
for package in os.listdir(base_dir):   #os.getcwd()):
    package_path = os.path.join(base_dir, package)
    if os.path.isdir(package_path):
        print(f'=== Package {package} ===')
        for file in os.listdir(package_path):  # os.getcwd()):
            if file.endswith(".py") and file[0] != '_':
                module_nm = re.sub(r'\.py','', file )
                print(f'  {module_nm}.py' )
                    
                module = importlib.import_module(module_nm, package=package)
                
                for item in inspect.getmembers(module, pred):
                    module_name = item[1]
                    if  item[0][0] != '_' and module_nm  in str(inspect.getmodule(item[1])):
                        print(f'      ({item[0]})' )
                        #display_modules(module_name)
                        for itm in inspect.getmembers(item[1], pred):
                            module_name = itm[1]
                            if itm[0][0] != '_' and module_nm  in str(inspect.getmodule(item[1])):
                                print(f'           <{itm[0]}>')
                                #print(f'                {itm[1].__doc__}\n' )
                                pass


