/*
    This file is part of the Arduino_RPClite library.

    Copyright (c) 2025 Arduino SA

    This Source Code Form is subject to the terms of the Mozilla Public
    License, v. 2.0. If a copy of the MPL was not distributed with this
    file, You can obtain one at http://mozilla.org/MPL/2.0/.
    
*/

#ifndef RPCLITE_SERVER_H
#define RPCLITE_SERVER_H

#include <utility>

#include "request.h"
#include "error.h"
#include "dispatcher.h"
#include "decoder.h"
#include "decoder_manager.h"

#define MAX_CALLBACKS   100

class RPCServer {

public:
    explicit RPCServer(ITransport& t) : decoder(&RpcDecoderManager<>::getDecoder(t)) {}

    template<typename F>
    bool bind(const MsgPack::str_t& name, F&& func, MsgPack::str_t tag=""){
        return dispatcher.bind(name, func, tag);
    }

    bool isBound(const MsgPack::str_t& name) const { return dispatcher.isBound(name); }

    bool hasTag(const MsgPack::str_t& name, MsgPack::str_t tag) const {
        return dispatcher.hasTag(name, tag);
    }

    bool run() {

        RPCRequest<> req;

        if (!get_rpc(req)) return false; // Populate local request

        process_request(req);      // Process local data

        return send_response(req);           // Send local data

    }

    template<size_t RpcSize = DEFAULT_RPC_BUFFER_SIZE>
    bool get_rpc(RPCRequest<RpcSize>& req, MsgPack::str_t tag="") {
        decoder->decode();

        const MsgPack::str_t method = decoder->fetch_rpc_method();

        if(method=="")return false;
        if(dispatcher.isBound(method)&&!dispatcher.hasTag(method,tag))return false;
        // Unknown calls must be consumed and answered with the existing
        // FUNCTION_NOT_FOUND path. A known wrong-tag call stays queued.
        if(!dispatcher.isBound(method))mic_rpc_inc(&mic_rpc_health.unknown_methods);

        req.size = decoder->get_request(req.buffer, RpcSize);
        return req.size > 0;
    }

    template<size_t RpcSize = DEFAULT_RPC_BUFFER_SIZE>
    void process_request(RPCRequest<RpcSize>& req) {

        mic_rpc_note(4,req.size,mic_rpc_prefix(req.buffer,req.size));
        if (!req.unpack_request_headers()) {
            mic_rpc_note(5,req.size);
            req.reset();
            return;
        }

        mic_rpc_note(6,req.msg_id,req.size,req.type);
        req.pack_response_headers();

        const bool dispatched=dispatcher.call(req.method, req.unpacker, req.packer);
        mic_rpc_note(7,req.msg_id,req.packer.size(),dispatched,req.type);

    }

    template<size_t RpcSize = DEFAULT_RPC_BUFFER_SIZE>
    bool send_response(const RPCRequest<RpcSize>& req) const {

        if (req.type == NO_MSG || req.packer.size() == 0) {
            return true; // No response to send
        }

        if (req.type == NOTIFY_MSG) return true;

        mic_rpc_note(8,req.msg_id,req.packer.size(),req.type);
        const bool sent=decoder->send_response(req.packer);
        mic_rpc_note(9,req.msg_id,req.packer.size(),sent,req.type);
        return sent;

    }

    uint32_t get_discarded_packets() const {return decoder->get_discarded_packets();}

private:
    RpcDecoder<>* decoder = nullptr;
    RpcFunctionDispatcher<MAX_CALLBACKS> dispatcher{};
    
};

#endif //RPCLITE_SERVER_H
