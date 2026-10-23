#pragma once
// Fixed-row binary output shared by native scene renderers. No image math,
// sampling, or transport policy belongs here; callers provide original bytes.
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace cybr_film {
enum class RowOrder { top_down, bottom_up };

struct RowLayout {
    std::string path, header;
    std::size_t row_bytes, height;
    RowOrder order = RowOrder::top_down;
};

class BinaryRows {
    std::fstream stream_;
    std::size_t header_bytes_, row_bytes_, height_;
    RowOrder order_;
    std::vector<bool> written_;
    bool finished_ = false;
public:
    BinaryRows(const std::string& path, const std::string& header,
               std::size_t row_bytes, std::size_t height,
               RowOrder order = RowOrder::top_down,
               bool resume = false, std::size_t committed_rows = 0)
        : header_bytes_(header.size()), row_bytes_(row_bytes), height_(height),
          order_(order), written_(height, false) {
        const auto maximum = static_cast<std::size_t>((std::numeric_limits<std::streamoff>::max)());
        if (!row_bytes || !height || header_bytes_ > maximum ||
            row_bytes > (maximum - header_bytes_) / height ||
            row_bytes > static_cast<std::size_t>((std::numeric_limits<std::streamsize>::max)()))
            throw std::invalid_argument("Invalid binary film dimensions");
        if(committed_rows > height || (!resume && committed_rows))
            throw std::invalid_argument("Invalid committed film rows");
        stream_.open(path, std::ios::binary | std::ios::in | std::ios::out |
                     (resume ? std::ios::openmode(0) : std::ios::trunc));
        if(resume) {
            std::string actual(header.size(), '\0');
            stream_.read(actual.data(), static_cast<std::streamsize>(actual.size()));
            if(!stream_ || actual != header) throw std::runtime_error("Resume film header mismatch");
            for(std::size_t y=0;y<committed_rows;y++) written_[y]=true;
        } else stream_.write(header.data(), static_cast<std::streamsize>(header.size()));
        if (!stream_) throw std::runtime_error("Cannot open binary film output: " + path);
    }

    explicit BinaryRows(const RowLayout& layout, bool resume=false, std::size_t rows=0)
        : BinaryRows(layout.path,layout.header,layout.row_bytes,layout.height,layout.order,resume,rows) {}

    // Checkpoint callers must validate the complete receipt before opening a
    // writer in resume mode. The renderer exposes no naked next-row CLI option.
    void flush_completed(std::size_t rows) {
        if(finished_ || rows > height_) throw std::logic_error("Invalid film flush boundary");
        for(std::size_t y=0;y<rows;y++)
            if(!written_[y]) throw std::logic_error("Checkpoint would include a missing film row");
        stream_.flush();
        if(!stream_) throw std::runtime_error("Cannot flush binary film output");
    }

    void write_row(std::size_t y, const void* bytes, std::size_t size) {
        if (finished_ || y >= height_ || size != row_bytes_ || !bytes)
            throw std::invalid_argument("Invalid binary film row");
        if (written_[y]) throw std::logic_error("Binary film row written twice");
        const std::size_t disk_y = order_ == RowOrder::bottom_up ? height_ - 1 - y : y;
        stream_.seekp(static_cast<std::streamoff>(header_bytes_ + disk_y * row_bytes_));
        stream_.write(static_cast<const char*>(bytes), static_cast<std::streamsize>(size));
        if (!stream_) throw std::runtime_error("Cannot write binary film row");
        written_[y] = true;
    }

    void finish() {
        if (finished_) throw std::logic_error("Binary film output already finished");
        for (bool row : written_)
            if (!row) throw std::logic_error("Binary film output has missing rows");
        stream_.flush();
        if (!stream_) throw std::runtime_error("Cannot flush binary film output");
        stream_.close();
        if (!stream_) throw std::runtime_error("Cannot close binary film output");
        finished_ = true;
    }
};
} // namespace cybr_film
