/*
    This file is part of the Arduino_RPClite library.

    Copyright (c) 2025 Arduino SA

    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was not distributed with this
    file, You can obtain one at http://mozilla.org/MPL/2.0/.
    
*/

#ifndef SERIALTRANSPORT_H
#define SERIALTRANSPORT_H
#include "transport.h"

class SerialTransport final : public ITransport {

    Stream* _stream;

    public:

        explicit SerialTransport(Stream* stream): _stream(stream){}

        explicit SerialTransport(Stream& stream): _stream(&stream){}

        bool available() override {
            return _stream->available();
        }

        size_t write(const uint8_t* data, size_t size) override {
            // Bridge serializes writers; never ask the core to block for
            // more bytes than its TX ring can accept immediately.
            const int room=_stream->availableForWrite();
            if(room<=0)return 0;
            const size_t n=size<(size_t)room?size:(size_t)room;
            return _stream->write(data,n);
        }

        size_t read(uint8_t* buffer, size_t size) override {
            _stream->setTimeout(0);
            return _stream->readBytes(buffer, size);
        }

        size_t read_byte(uint8_t& r) override {
            uint8_t b[1];
            if (read(b, 1) != 1){
                return 0;
            };
            r = b[0];
            return 1;
        }

};

#endif  //SERIALTRANSPORT_H