#include "native_film_output.hpp"
#include <array>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <iterator>

template<class E, class F> void rejects(F operation) {
    bool rejected=false;
    try { operation(); } catch(const E&) { rejected=true; }
    assert(rejected);
}

int main(int argc, char** argv) {
    assert(argc==2);
    const auto directory=std::filesystem::path(argv[1]);
    std::filesystem::create_directories(directory);
    const std::string header("binary\0header\n",14);
    const std::array<std::array<uint32_t,2>,3> rows{{{{1,2}},{{3,4}},{{5,6}}}};
    for(auto order : {cybr_film::RowOrder::top_down,cybr_film::RowOrder::bottom_up}) {
        const auto path=directory/(order==cybr_film::RowOrder::top_down ? "top.bin" : "bottom.bin");
        cybr_film::BinaryRows writer(path.string(),header,sizeof(rows[0]),rows.size(),order);
        // Completion order must not change the native record layout.
        writer.write_row(2,rows[2].data(),sizeof(rows[2]));
        writer.write_row(0,rows[0].data(),sizeof(rows[0]));
        rejects<std::logic_error>([&]{writer.write_row(0,rows[0].data(),sizeof(rows[0]));});
        rejects<std::logic_error>([&]{writer.finish();});
        rejects<std::invalid_argument>([&]{writer.write_row(3,rows[0].data(),sizeof(rows[0]));});
        rejects<std::invalid_argument>([&]{writer.write_row(1,rows[1].data(),sizeof(uint32_t));});
        rejects<std::invalid_argument>([&]{writer.write_row(1,nullptr,sizeof(rows[1]));});
        writer.write_row(1,rows[1].data(),sizeof(rows[1]));
        writer.finish();
        rejects<std::invalid_argument>([&]{writer.write_row(1,rows[1].data(),sizeof(rows[1]));});
        std::ifstream input(path,std::ios::binary);
        const std::string actual((std::istreambuf_iterator<char>(input)),std::istreambuf_iterator<char>());
        std::string expected=header;
        for(int y=0;y<3;y++) {
            const auto& row=rows[order==cybr_film::RowOrder::top_down ? y : 2-y];
            expected.append(reinterpret_cast<const char*>(row.data()),sizeof(row));
        }
        assert(actual==expected);
    }
    rejects<std::invalid_argument>([&]{cybr_film::BinaryRows bad((directory/"bad.bin").string(),header,0,3);});
    rejects<std::runtime_error>([&]{cybr_film::BinaryRows bad((directory/"absent"/"bad.bin").string(),header,8,3);});
}
