#include "cybr/io.hpp"
#include <cassert>
#include <iostream>
using namespace cybr;
int main(int argc,char**argv){assert(argc==3);Scene a,b;read_scene(argv[1],a);read_scene(argv[2],b);assert(a.primitives.size()==2&&b.primitives.size()==1);assert(b.primitives[0].object==11);assert(norm(b.primitives[0].geometry().a-a.primitives[1].geometry().a)<1e-12);std::cout<<"PASS exact meshlet component replacement, retained geometry unchanged\n";}
