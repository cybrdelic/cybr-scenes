#include "native_checkpoint.hpp"
#include <cassert>
#include <iostream>
#include <memory>

namespace fs=std::filesystem;
using cybr_film::BinaryRows;
using cybr_film::RowLayout;
using cybr_film::RowOrder;
using cybr_checkpoint::RowCheckpoint;

template<class F> void rejects(const char* label,F operation) {
    bool rejected=false;
    try { operation(); } catch(const std::exception&) { rejected=true; }
    if(!rejected) throw std::runtime_error(std::string("Did not reject: ")+label);
    std::cout<<"PASS reject "<<label<<"\n";
}
void write(const fs::path& path,const std::string& bytes) {
    std::ofstream file(path,std::ios::binary|std::ios::trunc);file.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));file.close();assert(file);
}
std::string read(const fs::path& path) { return cybr_checkpoint::read_small(path); }
std::string row(std::size_t y) { return std::string(32,static_cast<char>(y+13)); }

int main(int argc,char** argv) {
    if(argc==3&&std::string(argv[1])=="--hash") {std::cout<<cybr_checkpoint::file_sha256(argv[2])<<"\n";return 0;}
    assert(argc==2);
    const auto parent=fs::path(argv[1]);fs::create_directories(parent);
    const auto root=parent/("run-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    assert(fs::create_directory(root));
    using cybr_checkpoint::sha256;
    assert(sha256("")=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert(sha256("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    assert(sha256(std::string(1000000,'a'))=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    std::string binary;for(int i=0;i<256;i++)binary.push_back(char(i));write(root/"binary",binary);
    assert(cybr_checkpoint::file_sha256(root/"binary")=="40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880");
    std::cout<<"PASS SHA-256 published vectors and binary file\n";

    const std::string header("HDR\0",4),binding("source/executable/mesh/texture/config identity"),state("raw\0float-state",15);
    const std::vector<RowLayout> layouts{{(root/"top").string(),header,32,5,RowOrder::top_down},
                                         {(root/"bottom").string(),header,32,5,RowOrder::bottom_up}};
    const auto dir=root/"checkpoints";
    {
        RowCheckpoint checkpoint(dir,binding,layouts,2,false);
        BinaryRows top(layouts[0]),bottom(layouts[1]);std::vector<BinaryRows*> writers{&top,&bottom};
        checkpoint.commit(0,state,writers);
        // Missing rows must be rejected before they can acquire a receipt.
        rejects("missing output row",[&]{checkpoint.commit(2,state,writers);});
        for(std::size_t y=0;y<2;y++){const auto bytes=row(y);top.write_row(y,bytes.data(),bytes.size());bottom.write_row(y,bytes.data(),bytes.size());}
        checkpoint.commit(2,state,writers);
        rejects("duplicate boundary",[&]{checkpoint.commit(2,state,writers);});
        // A later partial tile has no receipt; it must never be mistaken for
        // completion. The resumed renderer overwrites these bytes at row 2.
        const auto tail=row(2);top.write_row(2,tail.data(),tail.size());bottom.write_row(2,tail.data(),tail.size());
        top.flush_completed(3);bottom.flush_completed(3);
    }
    auto latest=dir/"rows-0000000002.ready"/"state.bin";
    const auto receipt=read(latest),topBytes=read(root/"top"),bottomBytes=read(root/"bottom");
    auto load=[&]{return RowCheckpoint(dir,binding,layouts,2,true);};
    assert(load().state().next_row==2&&load().state().consumer_bytes==state);
    rejects("changed source/config identity",[&]{RowCheckpoint x(dir,binding+"changed",layouts,2,true);});
    for(const char* role:{"mesh","texture","source"}) {
        const auto input=root/role;write(input,"original");std::string before,after;
        cybr_checkpoint::bind_file(before,role,input);write(input,"modified");cybr_checkpoint::bind_file(after,role,input);
        assert(before!=after);std::cout<<"PASS changed "<<role<<" identity\n";
    }
    auto corrupt=receipt;corrupt[20]^=1;write(latest,corrupt);
    rejects("corrupt receipt",load);write(latest,receipt.substr(0,receipt.size()-1));
    rejects("truncated receipt",load);write(latest,receipt);
    auto badTop=topBytes;badTop[header.size()+3]^=1;write(root/"top",badTop);
    rejects("corrupt committed prefix",load);write(root/"top",topBytes);
    write(root/"top",topBytes.substr(0,header.size()+32));
    rejects("truncated committed prefix",load);write(root/"top",topBytes);
    auto badBottom=bottomBytes;badBottom[header.size()+4*32+7]^=1;write(root/"bottom",badBottom);
    rejects("corrupt committed bottom-up tail",load);write(root/"bottom",bottomBytes);
    write(root/"bottom",bottomBytes.substr(0,bottomBytes.size()-1));
    rejects("truncated bottom-up tail",load);write(root/"bottom",bottomBytes);
    auto badHeader=topBytes;badHeader[0]^=1;write(root/"top",badHeader);
    rejects("changed output header",load);write(root/"top",topBytes);
    // Partial uncommitted final row and an abandoned staging directory are
    // safe only because neither is considered committed; their bytes are redone.
    write(root/"top",topBytes.substr(0,header.size()+2*32+7));
    fs::create_directory(dir/"rows-0000000004.ready.pending-interrupted");
    write(dir/"rows-0000000004.ready.pending-interrupted"/"state.bin","partial");
    assert(load().state().next_row==2);
    {
        auto checkpoint=load();BinaryRows top(layouts[0],true,2),bottom(layouts[1],true,2);
        std::vector<BinaryRows*> writers{&top,&bottom};
        for(std::size_t y=2;y<4;y++){const auto bytes=row(y);top.write_row(y,bytes.data(),bytes.size());bottom.write_row(y,bytes.data(),bytes.size());}
        // Make publication impossible. The last trusted boundary must remain 2.
        fs::rename(dir,root/"retained-checkpoints");write(dir,"not a directory");
        rejects("receipt publication failure",[&]{checkpoint.commit(4,state,writers);});
        assert(checkpoint.state().next_row==2);
        fs::remove(dir);fs::rename(root/"retained-checkpoints",dir);
        checkpoint.commit(4,state,writers);
        const auto last=row(4);top.write_row(4,last.data(),last.size());bottom.write_row(4,last.data(),last.size());
        checkpoint.commit(5,state,writers);top.finish();bottom.finish();
    }
    assert(load().state().next_row==5);
    for(std::size_t i=0;i<layouts.size();i++){
        std::string expected=header;
        for(std::size_t y=0;y<5;y++)expected+=row(i==0?y:4-y);
        assert(read(layouts[i].path)==expected);
    }
    std::cout<<"PASS exact resumed rows, binary state, and non-tile-multiple height\n";
    fs::rename(dir/"rows-0000000002.ready",root/"withheld-boundary");
    rejects("missing committed boundary",load);
    fs::rename(root/"withheld-boundary",dir/"rows-0000000002.ready");
    // No fallback to an earlier receipt when the latest committed one is bad.
    latest=dir/"rows-0000000005.ready"/"state.bin";write(latest,"truncated");
    rejects("corrupt latest cannot silently roll back",load);
    std::cout<<"All checkpoint integrity tests passed\n";
}
