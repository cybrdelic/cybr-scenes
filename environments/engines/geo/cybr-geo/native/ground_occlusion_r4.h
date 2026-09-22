// SPDX-License-Identifier: GPL-2.0-only
// Conservative root interval and continuous-height-field sun-occlusion proof.
// A true result certifies zero reflected-solar contribution, not approximate GI.
#pragma once
struct GroundOcclusionR4 {
    bool active=false;
    uint32_t nx=0,ny=0;
    float x0=0,x1=0,y0=0,y1=0,zlo=0,zhi=0,dx=0,dy=0;
    double H=0,Sx=0,Sy=0;
    std::vector<uint32_t> prefix;
    std::atomic<uint64_t> queries{0},rejections{0};
    void load(const std::string &path){
        std::ifstream in(path,std::ios::binary);char magic[4];float b[6];
        in.read(magic,4);in.read(reinterpret_cast<char*>(&nx),4);in.read(reinterpret_cast<char*>(&ny),4);in.read(reinterpret_cast<char*>(b),24);
        if(!in||std::memcmp(magic,"GOC1",4)||nx<2||ny<2||nx>4096||ny>4096||uint64_t(nx)*ny>10000000)throw std::runtime_error("Invalid ground-occlusion certificate");
        for(float v:b)if(!std::isfinite(v))throw std::runtime_error("Nonfinite terrain bound");
        x0=b[0];x1=b[1];y0=b[2];y1=b[3];zlo=b[4];zhi=b[5];
        if(!(x1>x0&&y1>y0&&zhi>=zlo))throw std::runtime_error("Invalid terrain domain");
        dx=(x1-x0)/(nx-1);dy=(y1-y0)/(ny-1);
        for(V s:rippleFields[0].samples){H=std::max(H,double(std::fabs(s.x)));Sx=std::max(Sx,double(std::fabs(s.y)));Sy=std::max(Sy,double(std::fabs(s.z)));}
        // Bilinear interpolation is a convex combination; these bound its entire domain.
        H+=std::fabs(double(pools[0].level))+2.e-5;Sx+=2.e-5;Sy+=2.e-5;
        prefix.assign(size_t(nx)*ny,0);
        std::vector<float> row(nx-1);
        for(uint32_t y=0;y<ny-1;y++){
            in.read(reinterpret_cast<char*>(row.data()),row.size()*4);if(!in)throw std::runtime_error("Truncated terrain certificate");
            uint32_t sum=0;
            for(uint32_t x=0;x<nx-1;x++){
                if(!std::isfinite(row[x]))throw std::runtime_error("Nonfinite cell bound");
                // Includes much more than renderer origin offsets and root residual tolerance.
                sum+=row[x]<=H+.030;
                prefix[size_t(y+1)*nx+x+1]=prefix[size_t(y)*nx+x+1]+sum;
            }
        }
        char trailing;if(in.read(&trailing,1))throw std::runtime_error("Trailing terrain certificate data");
        active=true;
    }
    bool occludes(V p,V air){
        if(!active||p.z<=H+.05||air.z<=.08f)return false;
        queries.fetch_add(1,std::memory_order_relaxed);
        const double lx=air.x,ly=air.y,lz=air.z;
        const double bmin=lz-std::fabs(lx)*Sx-std::fabs(ly)*Sy,bmax=lz+std::fabs(lx)*Sx+std::fabs(ly)*Sy;
        if(bmin<=0)return false;
        const double rzmin=2*bmin/(1+Sx*Sx+Sy*Sy)-lz,rzmax=2*bmax-lz;
        if(rzmin<=.035||rzmax<=rzmin)return false;
        auto ratio=[&](double l,double s){
            const double lo=-l-2*bmax*s,hi=-l+2*bmax*s;
            std::array<double,4> values{lo/rzmin,lo/rzmax,hi/rzmin,hi/rzmax};
            return std::pair<double,double>(*std::min_element(values.begin(),values.end()),*std::max_element(values.begin(),values.end()));
        };
        const auto rx=ratio(lx,Sx),ry=ratio(ly,Sy);const double hlo=double(p.z)-H,hhi=double(p.z)+H;
        auto point_range=[&](double center,std::pair<double,double> r){
            std::array<double,4> v{hlo*r.first,hlo*r.second,hhi*r.first,hhi*r.second};
            return std::pair<double,double>(center-*std::max_element(v.begin(),v.end())-.02,center-*std::min_element(v.begin(),v.end())+.02);
        };
        auto qx=point_range(p.x,rx),qy=point_range(p.y,ry);
        // Require the complete ray up to above global terrain height to stay in its domain.
        // Then continuity proves that it crosses the opaque terrain before reaching the sun.
        double tlo=(zhi+.10-H)/lz,thi=(zhi+.10+H)/lz;
        auto end_range=[&](std::pair<double,double> q,double l){return std::pair<double,double>(q.first+std::min(tlo*l,thi*l),q.second+std::max(tlo*l,thi*l));};
        auto ex=end_range(qx,lx),ey=end_range(qy,ly);
        if(qx.first<=x0+.03||qx.second>=x1-.03||qy.first<=y0+.03||qy.second>=y1-.03||ex.first<=x0+.03||ex.second>=x1-.03||ey.first<=y0+.03||ey.second>=y1-.03)return false;
        int ax=int(std::floor((qx.first-x0)/dx))-1,bx=int(std::floor((qx.second-x0)/dx))+1;
        int ay=int(std::floor((qy.first-y0)/dy))-1,by=int(std::floor((qy.second-y0)/dy))+1;
        if(ax<0||ay<0||bx>=int(nx)-1||by>=int(ny)-1)return false;
        uint32_t eligible=prefix[size_t(by+1)*nx+bx+1]-prefix[size_t(ay)*nx+bx+1]-prefix[size_t(by+1)*nx+ax]+prefix[size_t(ay)*nx+ax];
        if(eligible)return false;
        rejections.fetch_add(1,std::memory_order_relaxed);return true;
    }
};
GroundOcclusionR4 groundOcclusion;
