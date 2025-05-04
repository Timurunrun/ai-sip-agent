import pjsua2 as pj
import logging

def create_endpoint():
    ep = pj.Endpoint()
    ep.libCreate()

    ep_cfg = pj.EpConfig()
    ep_cfg.logConfig.level = 2
    ep_cfg.logConfig.consoleLevel = 2
    ep_cfg.uaConfig.maxCalls = 4
    ep_cfg.uaConfig.userAgent = "Python SIP Agent"
    ep_cfg.medConfig.sndClockRate = 24000
    ep_cfg.medConfig.audioFramePtime = 20
    ep_cfg.medConfig.ecOptions = 0
    ep_cfg.medConfig.ecTailLen = 0

    ep.libInit(ep_cfg)

    transport_cfg = pj.TransportConfig()
    transport_cfg.port = 5060
    ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)

    ep.libStart()
    adm = ep.audDevManager()
    adm.refreshDevs()
    adm.setNullDev()
    logging.info("[PJSUA] Endpoint создан и настроен")
    return ep
