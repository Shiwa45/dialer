# telephony/services.py

import asyncio
import websockets
import json
import requests
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from .models import AsteriskServer, Phone, CallQueue, Recording
from calls.models import CallLog

logger = logging.getLogger(__name__)

class AsteriskService:
    """
    Service class for Asterisk integration via ARI and AMI
    """
    
    def __init__(self, server):
        self.server = server
        self.ari_base_url = f"http://{server.ari_host}:{server.ari_port}/ari"
        self.ami_host = server.ami_host
        self.ami_port = server.ami_port
        self.ami_username = server.ami_username
        self.ami_password = server.ami_password
        self.ari_username = server.ari_username
        self.ari_password = server.ari_password
        self.application = server.ari_application
    
    def test_connection(self):
        """
        Test connection to Asterisk server
        """
        try:
            # Test ARI connection
            # ARI base already ends with /ari; do not repeat it
            response = requests.get(
                f"{self.ari_base_url}/applications",
                auth=(self.ari_username, self.ari_password),
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'Connection successful',
                    'asterisk_info': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'ARI connection failed: {response.status_code}'
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Connection error: {str(e)}'
            }
    
    def get_server_status(self):
        """
        Get current server status and statistics
        """
        try:
            # Get Asterisk info
            response = requests.get(
                f"{self.ari_base_url}/asterisk/info",
                auth=(self.ari_username, self.ari_password),
                timeout=5
            )
            
            if response.status_code != 200:
                return {'status': 'error', 'message': 'Failed to connect'}
            
            asterisk_info = response.json()
            
            # Get channel count
            channels_response = requests.get(
                f"{self.ari_base_url}/channels",
                auth=(self.ari_username, self.ari_password),
                timeout=5
            )
            
            channels = channels_response.json() if channels_response.status_code == 200 else []
            
            # Get endpoint status
            endpoints_response = requests.get(
                f"{self.ari_base_url}/endpoints",
                auth=(self.ari_username, self.ari_password),
                timeout=5
            )
            
            endpoints = endpoints_response.json() if endpoints_response.status_code == 200 else []
            
            return {
                'status': 'connected',
                'asterisk_info': asterisk_info,
                'active_channels': len(channels),
                'total_endpoints': len(endpoints),
                'server_uptime': asterisk_info.get('startup_time'),
                'last_updated': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting server status: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def get_endpoint_status(self, extension):
        """
        Retrieve PJSIP endpoint registration/state information
        """
        try:
            response = requests.get(
                f"{self.ari_base_url}/endpoints/PJSIP/{extension}",
                auth=(self.ari_username, self.ari_password),
                timeout=5
            )
            if response.status_code == 200:
                payload = response.json()
                state = (payload.get('state') or '').lower()
                registered = state in ('online', 'reachable', 'available', 'ready')
                return {
                    'success': True,
                    'registered': registered,
                    'state': state,
                    'raw': payload
                }
            return {
                'success': False,
                'registered': False,
                'error': response.text
            }
        except Exception as e:
            logger.error(f"Error retrieving endpoint {extension} status: {str(e)}")
            return {
                'success': False,
                'registered': False,
                'error': str(e)
            }
    
    def originate_call(self, extension, phone_number, campaign=None, context='agents'):
        """
        Originate a call from agent extension to phone number
        """
        try:
            # Use PJSIP endpoint as we provision PJSIP in realtime
            call_data = {
                'endpoint': f'PJSIP/{extension}',
                'extension': phone_number,
                'context': context,
                'priority': 1,
                'callerId': f'Agent {extension}',
                'timeout': 30,
                'variables': {
                    'CAMPAIGN_ID': str(campaign.id) if campaign else '',
                    'AGENT_EXTENSION': extension,
                    'CALL_TYPE': 'outbound'
                }
            }
            
            response = requests.post(
                f"{self.ari_base_url}/channels",
                auth=(self.ari_username, self.ari_password),
                json=call_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                channel_data = response.json()
                
                # Log the call
                call_log = CallLog.objects.create(
                    caller_id=str(extension),
                    called_number=phone_number,
                    campaign=campaign,
                    asterisk_server=self.server,
                    call_type='outbound',
                    call_status='initiated',
                    start_time=timezone.now(),
                    channel=channel_data.get('id') or ''
                )
                
                return {
                    'success': True,
                    'channel_id': channel_data.get('id'),
                    'call_log_id': call_log.id
                }
            else:
                return {
                    'success': False,
                    'error': f'Failed to originate call: {response.text}'
                }
                
        except Exception as e:
            logger.error(f"Error originating call: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    # =====================
    # ARI Bridge Utilities
    # =====================
    def _ari_post(self, path, json_body=None, timeout=10):
        return requests.post(
            f"{self.ari_base_url}{path}",
            auth=(self.ari_username, self.ari_password),
            json=json_body or {},
            timeout=timeout
        )

    def _ari_delete(self, path, timeout=10):
        return requests.delete(
            f"{self.ari_base_url}{path}",
            auth=(self.ari_username, self.ari_password),
            timeout=timeout
        )

    def create_bridge(self, bridge_type='mixing'):  # returns bridge_id
        try:
            r = self._ari_post("/bridges", json_body={"type": bridge_type})
            if r.status_code in (200, 201):
                return {"success": True, "bridge_id": r.json().get('id')}
            return {"success": False, "error": f"Bridge create failed: {r.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_channel_to_bridge(self, bridge_id, channel_id):
        try:
            r = self._ari_post(f"/bridges/{bridge_id}/addChannel", json_body={"channel": channel_id})
            if r.status_code in (200, 204):
                return {"success": True}
            return {"success": False, "error": f"Add channel failed: {r.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def originate_pjsip_channel(self, endpoint, app='autodialer', callerid=None, variables=None, timeout=30):
        try:
            payload = {
                'endpoint': f'PJSIP/{endpoint}',
                'app': app,
                'callerId': callerid or endpoint,
                'timeout': timeout,
            }
            if variables:
                payload['variables'] = variables
                # Also pass critical routing info in appArgs so StasisStart args are populated
                args = []
                if 'CALL_TYPE' in variables:
                    args.append(f"CALL_TYPE={variables['CALL_TYPE']}")
                if 'BRIDGE_ID' in variables:
                    args.append(f"BRIDGE_ID={variables['BRIDGE_ID']}")
                if args:
                    payload['appArgs'] = ','.join(args)
            r = self._ari_post("/channels", json_body=payload, timeout=timeout+5)
            if r.status_code in (200, 201):
                return {"success": True, "channel_id": r.json().get('id')}
            return {"success": False, "error": f"Originate failed: {r.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def originate_local_channel(self, number, context='from-campaign', app='autodialer', callerid=None, variables=None, timeout=45):
        """
        Originate using Local/number@context so PBX dialplan handles routing.
        Use this for prefix-based routing to GSM gateways (Dinstar/OpenVox).
        """
        try:
            payload = {
                'endpoint': f'Local/{number}@{context}',
                'app': app,
                'callerId': callerid or number,
                'timeout': timeout,
            }
            if variables:
                payload['variables'] = variables
                args = []
                if 'CALL_TYPE' in variables:
                    args.append(f"CALL_TYPE={variables['CALL_TYPE']}")
                if 'BRIDGE_ID' in variables:
                    args.append(f"BRIDGE_ID={variables['BRIDGE_ID']}")
                if args:
                    payload['appArgs'] = ','.join(args)

            r = self._ari_post("/channels", json_body=payload, timeout=timeout+5)
            if r.status_code in (200, 201):
                return {"success": True, "channel_id": r.json().get('id')}
            return {"success": False, "error": f"Originate Local failed: {r.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def hangup_channel(self, channel_id):
        try:
            r = self._ari_delete(f"/channels/{channel_id}")
            if r.status_code in (200, 204):
                return {"success": True}
            return {"success": False, "error": f"Hangup failed: {r.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =====================
    # ARI Helpers for polling
    # =====================
    def get_channel(self, channel_id):
        try:
            resp = requests.get(f"{self.ari_base_url}/channels/{channel_id}", auth=(self.ari_username, self.ari_password), timeout=5)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"{resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def wait_for_channel_up(self, channel_id, timeout_sec=30, interval=0.5):
        import time
        end = time.time() + timeout_sec
        while time.time() < end:
            info = self.get_channel(channel_id)
            if info.get('success'):
                state = (info['data'] or {}).get('state')
                if state == 'Up':
                    return {"success": True}
            time.sleep(interval)
        return {"success": False, "error": "Timeout waiting for channel Up"}

    
    def hangup_call(self, channel_id):
        """
        Hangup a specific call
        """
        try:
            response = requests.delete(
                f"{self.ari_base_url}/channels/{channel_id}",
                auth=(self.ari_username, self.ari_password),
                timeout=10
            )
            
            if response.status_code == 204:
                # Update call log
                try:
                    call_log = CallLog.objects.get(channel_id=channel_id)
                    call_log.call_status = 'hungup'
                    call_log.end_time = timezone.now()
                    call_log.save()
                except CallLog.DoesNotExist:
                    pass
                
                return {'success': True}
            else:
                return {
                    'success': False,
                    'error': f'Failed to hangup call: {response.text}'
                }
                
        except Exception as e:
            logger.error(f"Error hanging up call: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def transfer_call(self, channel_id, destination, transfer_type='blind'):
        """
        Transfer a call to another extension or number
        """
        try:
            if transfer_type == 'blind':
                # Blind transfer
                response = requests.post(
                    f"{self.ari_base_url}/channels/{channel_id}/redirect",
                    auth=(self.ari_username, self.ari_password),
                    json={
                        'endpoint': destination
                    },
                    timeout=10
                )
            else:
                # Attended transfer (more complex, requires bridge)
                response = requests.post(
                    f"{self.ari_base_url}/channels/{channel_id}/dial",
                    auth=(self.ari_username, self.ari_password),
                    json={
                        'endpoint': destination,
                        'timeout': 30
                    },
                    timeout=10
                )
            
            if response.status_code in [200, 204]:
                return {'success': True}
            else:
                return {
                    'success': False,
                    'error': f'Failed to transfer call: {response.text}'
                }
                
        except Exception as e:
            logger.error(f"Error transferring call: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_active_calls(self):
        """
        Get list of active calls on the server
        """
        try:
            response = requests.get(
                f"{self.ari_base_url}/channels",
                auth=(self.ari_username, self.ari_password),
                timeout=5
            )
            
            if response.status_code == 200:
                channels = response.json()
                active_calls = []
                
                for channel in channels:
                    call_info = {
                        'channel_id': channel.get('id'),
                        'caller_id': channel.get('caller', {}).get('number'),
                        'connected_line': channel.get('connected', {}).get('number'),
                        'state': channel.get('state'),
                        'created': channel.get('creationtime'),
                        'duration': self._calculate_duration(channel.get('creationtime'))
                    }
                    active_calls.append(call_info)
                
                return {
                    'success': True,
                    'calls': active_calls
                }
            else:
                return {
                    'success': False,
                    'error': f'Failed to get active calls: {response.text}'
                }
                
        except Exception as e:
            logger.error(f"Error getting active calls: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_queue_status(self, queue_name):
        """
        Get status of a specific call queue
        """
        try:
            # This would typically use AMI for queue status
            # For now, return basic info
            return {
                'success': True,
                'queue_name': queue_name,
                'waiting_calls': 0,
                'available_agents': 0,
                'logged_in_agents': 0
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _calculate_duration(self, creation_time):
        """
        Calculate call duration from creation time
        """
        if not creation_time:
            return 0
        
        try:
            created = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
            now = datetime.now(created.tzinfo)
            return int((now - created).total_seconds())
        except:
            return 0


class WebRTCService:
    """
    Service class for WebRTC phone management
    """
    
    def __init__(self, phone):
        self.phone = phone
        self.server = phone.asterisk_server
    
    def get_webrtc_config(self):
        """
        Get WebRTC configuration for the phone
        """
        try:
            config = {
                'success': True,
                'extension': self.phone.extension,
                'username': self.phone.extension,
                'password': self.phone.secret,
                'server': self.server.server_ip,
                'port': 8089,  # WebSocket port
                'protocol': 'wss',
                'ice_servers': [
                    {'urls': 'stun:stun.l.google.com:19302'},
                ],
                'audio_codecs': ['ulaw', 'alaw', 'opus'],
                'video_codecs': ['vp8', 'h264'] if self.phone.webrtc_enabled else [],
                'dtmf_mode': 'rfc2833'
            }
            
            if self.phone.ice_host:
                config['ice_servers'].append({
                    'urls': f'turn:{self.phone.ice_host}',
                    'username': 'turnuser',
                    'credential': 'turnpass'
                })
            
            return config
            
        except Exception as e:
            logger.error(f"Error getting WebRTC config: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def register_webrtc_phone(self):
        """
        Register WebRTC phone with Asterisk
        """
        try:
            # This would typically involve SIP registration
            # For now, just return success
            return {
                'success': True,
                'message': f'WebRTC phone {self.phone.extension} registered'
            }
            
        except Exception as e:
            logger.error(f"Error registering WebRTC phone: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


class CallRecordingService:
    """
    Service class for call recording management
    """
    
    def __init__(self, server):
        self.server = server
    
    def start_recording(self, channel_id, filename=None):
        """
        Start recording a call
        """
        try:
            if not filename:
                filename = f"recording_{channel_id}_{int(timezone.now().timestamp())}"
            
            recording_data = {
                'name': filename,
                'format': 'wav',
                'maxDurationSeconds': 3600,  # 1 hour max
                'maxSilenceSeconds': 10,
                'ifExists': 'overwrite'
            }
            
            asterisk_service = AsteriskService(self.server)
            response = requests.post(
                f"{asterisk_service.ari_base_url}/channels/{channel_id}/record",
                auth=(asterisk_service.ari_username, asterisk_service.ari_password),
                json=recording_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                recording_info = response.json()
                
                # Create recording record
                recording = Recording.objects.create(
                    call_id=channel_id,
                    filename=filename,
                    file_format='wav',
                    asterisk_server=self.server,
                    recording_start=timezone.now()
                )
                
                return {
                    'success': True,
                    'recording_id': recording.id,
                    'filename': filename
                }
            else:
                return {
                    'success': False,
                    'error': f'Failed to start recording: {response.text}'
                }
                
        except Exception as e:
            logger.error(f"Error starting recording: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def stop_recording(self, channel_id, recording_name):
        """
        Stop recording a call
        """
        try:
            asterisk_service = AsteriskService(self.server)
            response = requests.delete(
                f"{asterisk_service.ari_base_url}/recordings/live/{recording_name}",
                auth=(asterisk_service.ari_username, asterisk_service.ari_password),
                timeout=10
            )
            
            if response.status_code == 204:
                # Update recording record
                try:
                    recording = Recording.objects.get(
                        call_id=channel_id,
                        filename=recording_name
                    )
                    recording.recording_end = timezone.now()
                    recording.is_available = True
                    recording.save()
                except Recording.DoesNotExist:
                    pass
                
                return {'success': True}
            else:
                return {
                    'success': False,
                    'error': f'Failed to stop recording: {response.text}'
                }
                
        except Exception as e:
            logger.error(f"Error stopping recording: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


class DialplanService:
    """
    Service class for dialplan management
    """
    
    def __init__(self, server):
        self.server = server
    
    def generate_campaign_dialplan(self, campaign):
        """
        Generate dialplan configuration for a campaign
        """
        try:
            dialplan_config = []
            
            # Main campaign context
            context_name = f"campaign_{campaign.id}"
            
            # Extension for campaign entry
            extension_config = {
                'context': context_name,
                'extension': '_X.',
                'priority': 1,
                'application': 'Answer',
                'arguments': ''
            }
            dialplan_config.append(extension_config)
            
            # Set channel variables
            extension_config = {
                'context': context_name,
                'extension': '_X.',
                'priority': 2,
                'application': 'Set',
                'arguments': f'CAMPAIGN_ID={campaign.id}'
            }
            dialplan_config.append(extension_config)
            
            # Start recording if enabled
            if campaign.enable_recording:
                extension_config = {
                    'context': context_name,
                    'extension': '_X.',
                    'priority': 3,
                    'application': 'MixMonitor',
                    'arguments': f'{campaign.id}_${UNIQUEID}.wav'
                }
                dialplan_config.append(extension_config)
            
            # Connect to agent
            extension_config = {
                'context': context_name,
                'extension': '_X.',
                'priority': 4,
                'application': 'Dial',
                'arguments': 'SIP/${AGENT_EXTENSION},30'
            }
            dialplan_config.append(extension_config)
            
            # Hangup
            extension_config = {
                'context': context_name,
                'extension': '_X.',
                'priority': 5,
                'application': 'Hangup',
                'arguments': ''
            }
            dialplan_config.append(extension_config)
            
            return {
                'success': True,
                'dialplan': dialplan_config
            }
            
        except Exception as e:
            logger.error(f"Error generating dialplan: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def reload_dialplan(self):
        """
        Reload Asterisk dialplan
        """
        try:
            # This would typically use AMI to reload dialplan
            # For now, just return success
            return {
                'success': True,
                'message': 'Dialplan reloaded successfully'
            }
            
        except Exception as e:
            logger.error(f"Error reloading dialplan: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


class QueueService:
    """
    Service class for call queue management
    """
    
    def __init__(self, queue):
        self.queue = queue
        self.server = queue.asterisk_server
    
    def add_member(self, phone, penalty=0, paused=False):
        """
        Add a member to the queue
        """
        try:
            # This would typically use AMI QueueAdd command
            # For now, just create the database record
            from .models import QueueMember
            
            member, created = QueueMember.objects.get_or_create(
                queue=self.queue,
                phone=phone,
                defaults={
                    'penalty': penalty,
                    'is_paused': paused
                }
            )
            
            return {
                'success': True,
                'member_id': member.id,
                'created': created
            }
            
        except Exception as e:
            logger.error(f"Error adding queue member: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def remove_member(self, phone):
        """
        Remove a member from the queue
        """
        try:
            from .models import QueueMember
            
            member = QueueMember.objects.get(
                queue=self.queue,
                phone=phone
            )
            member.delete()
            
            return {'success': True}
            
        except QueueMember.DoesNotExist:
            return {
                'success': False,
                'error': 'Member not found in queue'
            }
        except Exception as e:
            logger.error(f"Error removing queue member: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def pause_member(self, phone, paused=True):
        """
        Pause/unpause a queue member
        """
        try:
            from .models import QueueMember
            
            member = QueueMember.objects.get(
                queue=self.queue,
                phone=phone
            )
            member.is_paused = paused
            member.save()
            
            return {'success': True}
            
        except QueueMember.DoesNotExist:
            return {
                'success': False,
                'error': 'Member not found in queue'
            }
        except Exception as e:
            logger.error(f"Error pausing queue member: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_queue_stats(self):
        """
        Get queue statistics
        """
        try:
            stats = {
                'total_members': self.queue.members.count(),
                'available_members': self.queue.members.filter(is_paused=False).count(),
                'paused_members': self.queue.members.filter(is_paused=True).count(),
                'waiting_calls': 0,  # Would come from Asterisk
                'completed_calls': 0,  # Would come from call logs
                'abandoned_calls': 0,  # Would come from call logs
                'average_wait_time': 0,  # Would be calculated
                'average_talk_time': 0,  # Would be calculated
            }
            
            return {
                'success': True,
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Error getting queue stats: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


class TelephonyMonitorService:
    """
    Service class for real-time telephony monitoring
    """
    
    def __init__(self):
        self.active_connections = set()
    
    async def start_monitoring(self, websocket_url):
        """
        Start WebSocket monitoring of Asterisk events
        """
        try:
            async with websockets.connect(websocket_url) as websocket:
                self.active_connections.add(websocket)
                
                async for message in websocket:
                    try:
                        event_data = json.loads(message)
                        await self.handle_asterisk_event(event_data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {message}")
                    except Exception as e:
                        logger.error(f"Error handling event: {str(e)}")
                        
        except Exception as e:
            logger.error(f"WebSocket monitoring error: {str(e)}")
        finally:
            self.active_connections.discard(websocket)
    
    async def handle_asterisk_event(self, event_data):
        """
        Handle incoming Asterisk events
        """
        event_type = event_data.get('type')
        
        if event_type == 'ChannelCreated':
            await self.handle_channel_created(event_data)
        elif event_type == 'ChannelDestroyed':
            await self.handle_channel_destroyed(event_data)
        elif event_type == 'ChannelStateChange':
            await self.handle_channel_state_change(event_data)
        # Add more event handlers as needed
    
    async def handle_channel_created(self, event_data):
        """
        Handle channel creation event
        """
        channel = event_data.get('channel', {})
        channel_id = channel.get('id')
        
        if channel_id:
            # Update call log or create new one
            try:
                call_log, created = CallLog.objects.get_or_create(
                    channel_id=channel_id,
                    defaults={
                        'caller_id': channel.get('caller', {}).get('number', ''),
                        'called_number': channel.get('dialplan', {}).get('exten', ''),
                        'call_status': 'ringing',
                        'call_direction': 'inbound'  # Default, can be updated
                    }
                )
                logger.info(f"Channel created: {channel_id}")
            except Exception as e:
                logger.error(f"Error creating call log: {str(e)}")
    
    async def handle_channel_destroyed(self, event_data):
        """
        Handle channel destruction event
        """
        channel = event_data.get('channel', {})
        channel_id = channel.get('id')
        
        if channel_id:
            try:
                call_log = CallLog.objects.get(channel_id=channel_id)
                call_log.call_status = 'completed'
                call_log.end_time = timezone.now()
                
                # Calculate duration
                if call_log.answer_time:
                    duration = (call_log.end_time - call_log.answer_time).total_seconds()
                    call_log.talk_duration = int(duration)
                
                call_log.save()
                logger.info(f"Channel destroyed: {channel_id}")
            except CallLog.DoesNotExist:
                logger.warning(f"Call log not found for channel: {channel_id}")
            except Exception as e:
                logger.error(f"Error updating call log: {str(e)}")
    
    async def handle_channel_state_change(self, event_data):
        """
        Handle channel state change event
        """
        channel = event_data.get('channel', {})
        channel_id = channel.get('id')
        new_state = channel.get('state')
        
        if channel_id and new_state:
            try:
                call_log = CallLog.objects.get(channel_id=channel_id)
                
                if new_state == 'Up' and not call_log.answer_time:
                    call_log.answer_time = timezone.now()
                    call_log.call_status = 'answered'
                elif new_state == 'Ringing':
                    call_log.call_status = 'ringing'
                
                call_log.save()
                logger.info(f"Channel state changed: {channel_id} -> {new_state}")
            except CallLog.DoesNotExist:
                logger.warning(f"Call log not found for channel: {channel_id}")
            except Exception as e:
                logger.error(f"Error updating call state: {str(e)}")


# Utility functions
def get_asterisk_service(server_id):
    """
    Get AsteriskService instance for a server
    """
    try:
        server = AsteriskServer.objects.get(id=server_id, is_active=True)
        return AsteriskService(server)
    except AsteriskServer.DoesNotExist:
        return None

def get_webrtc_service(phone_id):
    """
    Get WebRTCService instance for a phone
    """
    try:
        phone = Phone.objects.get(id=phone_id, is_active=True, webrtc_enabled=True)
        return WebRTCService(phone)
    except Phone.DoesNotExist:
        return None
