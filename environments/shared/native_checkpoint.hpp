#pragma once
// Integrity and ordered-row persistence only. Sampling/transport/film math stay
// in the consumer. Checkpoints detect corruption; they are not signatures.
#include "native_film_output.hpp"
#include "third_party/picosha2/picosha2.h"
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iomanip>
#include <sstream>

namespace cybr_checkpoint {
namespace fs = std::filesystem;

inline std::string sha256(const std::string& bytes) {
    return picosha2::hash256_hex_string(bytes);
}
inline void hash_range(picosha2::hash256_one_by_one& hash, std::ifstream& file,
                       uint64_t offset, uint64_t length) {
    file.clear(); file.seekg(static_cast<std::streamoff>(offset));
    std::array<char,65536> buffer{};
    while(length) {
        const auto n=static_cast<std::streamsize>((std::min)(length,uint64_t(buffer.size())));
        file.read(buffer.data(),n);
        if(!file || file.gcount()!=n) throw std::runtime_error("Truncated hash input");
        hash.process(buffer.data(),buffer.data()+n); length-=uint64_t(n);
    }
}
inline std::string file_sha256(const fs::path& path) {
    std::ifstream file(path,std::ios::binary);
    if(!file) throw std::runtime_error("Cannot hash required input: "+path.string());
    const auto before=fs::file_size(path);
    const auto modified=fs::last_write_time(path);
    picosha2::hash256_one_by_one hash; hash_range(hash,file,0,before); hash.finish();
    if(fs::file_size(path)!=before || fs::last_write_time(path)!=modified) throw std::runtime_error("Hash input changed while reading");
    return picosha2::get_hash_hex_string(hash);
}

// Length-prefixed binary fields prevent ambiguous concatenations; integer wire
// fields are little-endian. Consumer state is opaque exact bytes, never JSON floats.
inline void put_u64(std::string& into,uint64_t value) {
    for(int i=0;i<8;i++) into.push_back(static_cast<char>((value>>(8*i))&255));
}
inline void put_bytes(std::string& into,const std::string& value) {
    put_u64(into,value.size()); into+=value;
}
class Reader {
    const std::string& bytes_; std::size_t pos_=0;
public:
    explicit Reader(const std::string& bytes):bytes_(bytes) {}
    uint64_t u64() {
        if(bytes_.size()-pos_<8) throw std::runtime_error("Truncated checkpoint integer");
        uint64_t v=0; for(int i=0;i<8;i++) v|=uint64_t(static_cast<unsigned char>(bytes_[pos_++]))<<(8*i);
        return v;
    }
    std::string bytes() {
        const auto n=u64();
        if(n>bytes_.size()-pos_) throw std::runtime_error("Truncated checkpoint field");
        auto value=bytes_.substr(pos_,static_cast<std::size_t>(n)); pos_+=static_cast<std::size_t>(n); return value;
    }
    void end() const { if(pos_!=bytes_.size()) throw std::runtime_error("Trailing checkpoint bytes"); }
};
inline void bind_file(std::string& binding,const std::string& role,const fs::path& path) {
    put_bytes(binding,role); put_bytes(binding,file_sha256(path));
}
inline std::string read_small(const fs::path& path) {
    if(!fs::is_regular_file(path) || fs::file_size(path)>1024*1024)
        throw std::runtime_error("Missing or oversized checkpoint");
    std::ifstream stream(path,std::ios::binary);
    std::string bytes(static_cast<std::size_t>(fs::file_size(path)),'\0');
    stream.read(bytes.data(),static_cast<std::streamsize>(bytes.size()));
    if(!stream) throw std::runtime_error("Cannot read checkpoint");
    return bytes;
}

inline std::string layout_identity(const cybr_film::RowLayout& layout) {
    std::string s;
    put_bytes(s,fs::absolute(layout.path).lexically_normal().generic_u8string());
    put_bytes(s,layout.header); put_u64(s,layout.row_bytes); put_u64(s,layout.height);
    put_u64(s,layout.order==cybr_film::RowOrder::bottom_up?1:0); return s;
}
inline std::string committed_hash(const cybr_film::RowLayout& layout,std::size_t rows) {
    if(!layout.height || !layout.row_bytes || rows>layout.height ||
       layout.row_bytes>((std::numeric_limits<uint64_t>::max)()-layout.header.size())/layout.height)
        throw std::runtime_error("Invalid checkpoint film layout");
    const auto header=uint64_t(layout.header.size()), row=uint64_t(layout.row_bytes);
    const auto maximum=header+row*layout.height;
    const auto size=fs::file_size(layout.path);
    const auto minimum=header+row*(layout.order==cybr_film::RowOrder::bottom_up && rows?layout.height:rows);
    if(size<minimum || size>maximum) throw std::runtime_error("Truncated or oversized checkpoint film: "+layout.path);
    std::ifstream file(layout.path,std::ios::binary);
    std::string actual(layout.header.size(),'\0'); file.read(actual.data(),static_cast<std::streamsize>(actual.size()));
    if(!file || actual!=layout.header) throw std::runtime_error("Checkpoint film header mismatch");
    picosha2::hash256_one_by_one hash;
    hash.process(actual.begin(),actual.end());
    const auto offset=header+(layout.order==cybr_film::RowOrder::bottom_up?row*(layout.height-rows):0);
    hash_range(hash,file,offset,row*rows); hash.finish();
    return picosha2::get_hash_hex_string(hash);
}

struct State { std::size_t next_row=0; std::string consumer_bytes; };

class RowCheckpoint {
    fs::path directory_;
    std::string binding_;
    std::vector<cybr_film::RowLayout> layouts_;
    std::size_t height_,tile_rows_;
    State state_;
    bool has_state_=false;

    std::string name(std::size_t row) const {
        std::ostringstream s; s<<"rows-"<<std::setfill('0')<<std::setw(10)<<row<<".ready"; return s.str();
    }
    std::string encode(std::size_t next,const std::string& consumer) const {
        std::string bytes;
        put_bytes(bytes,"CYBR-ROW-CHECKPOINT-1"); put_bytes(bytes,binding_);
        put_u64(bytes,height_); put_u64(bytes,tile_rows_); put_u64(bytes,next);
        put_bytes(bytes,consumer); put_u64(bytes,layouts_.size());
        for(const auto& layout:layouts_) {
            put_bytes(bytes,layout_identity(layout)); put_bytes(bytes,committed_hash(layout,next));
        }
        return bytes+sha256(bytes);
    }
    State decode(const fs::path& path,bool verify_outputs) const {
        auto bytes=read_small(path);
        if(bytes.size()<64) throw std::runtime_error("Truncated checkpoint checksum");
        const auto expected=bytes.substr(bytes.size()-64); bytes.resize(bytes.size()-64);
        if(sha256(bytes)!=expected) throw std::runtime_error("Checkpoint checksum mismatch");
        Reader r(bytes);
        if(r.bytes()!="CYBR-ROW-CHECKPOINT-1" || r.bytes()!=binding_)
            throw std::runtime_error("Checkpoint source/input/config identity mismatch");
        if(r.u64()!=height_ || r.u64()!=tile_rows_) throw std::runtime_error("Checkpoint dimensions mismatch");
        const auto next=r.u64();
        if(next>height_ || (next!=height_ && next%tile_rows_)) throw std::runtime_error("Invalid checkpoint boundary");
        State state{static_cast<std::size_t>(next),r.bytes()};
        if(state.consumer_bytes.size()>4096 || r.u64()!=layouts_.size()) throw std::runtime_error("Checkpoint state/output mismatch");
        for(const auto& layout:layouts_) {
            if(r.bytes()!=layout_identity(layout)) throw std::runtime_error("Checkpoint output layout mismatch");
            const auto hash=r.bytes();
            if(hash.size()!=64 || (verify_outputs && hash!=committed_hash(layout,state.next_row)))
                throw std::runtime_error("Committed film range checksum mismatch: "+layout.path);
        }
        r.end(); return state;
    }
public:
    RowCheckpoint(const fs::path& directory,std::string binding,
                  std::vector<cybr_film::RowLayout> layouts,std::size_t tile_rows,bool resume)
        :directory_(directory),binding_(std::move(binding)),layouts_(std::move(layouts)),
         height_(layouts_.empty()?0:layouts_[0].height),tile_rows_(tile_rows) {
        if(!height_ || !tile_rows_ || layouts_.empty()) throw std::runtime_error("Invalid checkpoint layout");
        for(const auto& layout:layouts_) if(layout.height!=height_) throw std::runtime_error("Inconsistent film heights");
        if(!resume) {
            for(const auto& layout:layouts_) if(fs::exists(layout.path)) throw std::runtime_error("Refusing to overwrite existing film");
            if(!fs::create_directory(directory_)) throw std::runtime_error("Checkpoint directory must be new");
            return;
        }
        if(!fs::is_directory(directory_)) throw std::runtime_error("Missing checkpoint directory");
        std::vector<fs::path> receipts;
        for(const auto& entry:fs::directory_iterator(directory_))
            if(entry.path().extension()==".ready") receipts.push_back(entry.path());
        std::sort(receipts.begin(),receipts.end());
        if(receipts.empty()) throw std::runtime_error("No committed checkpoint; old partial films cannot be resumed");
        std::size_t expected=0;
        for(std::size_t i=0;i<receipts.size();i++) {
            if(receipts[i].filename()!=name(expected)) throw std::runtime_error("Missing or unexpected checkpoint boundary");
            state_=decode(receipts[i]/"state.bin",i+1==receipts.size());
            if(state_.next_row!=expected) throw std::runtime_error("Checkpoint filename/state mismatch");
            if(expected==height_ && i+1<receipts.size()) throw std::runtime_error("Checkpoint after final row");
            expected=(std::min)(expected+tile_rows_,height_);
        }
        has_state_=true;
    }
    const State& state() const { return state_; }

    void commit(std::size_t next,const std::string& consumer,const std::vector<cybr_film::BinaryRows*>& writers) {
        const auto expected=has_state_?(std::min)(state_.next_row+tile_rows_,height_):0;
        if(next!=expected || (has_state_ && state_.next_row==height_) || consumer.size()>4096 || writers.size()!=layouts_.size())
            throw std::runtime_error("Out-of-order checkpoint commit");
        for(auto* writer:writers) writer->flush_completed(next);
        const auto bytes=encode(next,consumer);
        const auto final=directory_/name(next);
        if(fs::exists(final)) throw std::runtime_error("Refusing to replace immutable checkpoint");
        // Publish a fully closed file by renaming its exclusively owned staging
        // directory to a new, immutable boundary name. No rename-over-existing.
        fs::path stage;
        for(unsigned attempt=0;attempt<100;attempt++) {
            const auto nonce=std::chrono::steady_clock::now().time_since_epoch().count();
            stage=directory_/(name(next)+".pending-"+std::to_string(nonce)+"-"+std::to_string(attempt));
            if(fs::create_directory(stage)) break;
            stage.clear();
        }
        if(stage.empty()) throw std::runtime_error("Cannot reserve checkpoint staging directory");
        std::ofstream file(stage/"state.bin",std::ios::binary|std::ios::trunc);
        file.write(bytes.data(),static_cast<std::streamsize>(bytes.size())); file.flush();
        if(!file) throw std::runtime_error("Checkpoint receipt write failed; boundary not committed");
        file.close(); if(!file) throw std::runtime_error("Checkpoint receipt close failed; boundary not committed");
        fs::rename(stage,final); // failed publication leaves only an uncommitted staging directory
        state_={next,consumer}; has_state_=true;
    }
};
} // namespace cybr_checkpoint
