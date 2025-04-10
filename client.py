import socket
import threading
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor

# Server connection config
SERVER_HOST = "ccscloud.dlsu.edu.ph"
SERVER_PORT = 31214

TOTAL_POINTS = 18
PLAZA_POINTS = [0, 17]
BOOTHS_PER_PLAZA = 6
BOOTHS_PER_REGULAR = 4

# Vehicle entry delay config
MIN_ENTRY_DELAY = 6  
MAX_ENTRY_DELAY = 20

# Vehicle generation config
VEHICLE_TYPES = ["CAR", "SUV", "TRUCK", "VAN", "BUS"]
VEHICLE_MAX_DIGITS = 3  # 000 - 999
MAX_VEHICLES = 30      # Vehicles to generate

# Control variables
running = True
startup_complete = False  # for booth connetion readiness
startup_barrier = None    # thread barrier for synced startup

# vehicle tracking for unique values
generated_vehicles = set()
vehicle_lock = threading.Lock()

# Counter for total vehicles
vehicles_generated = 0
vehicles_generated_lock = threading.Lock()

# assign booth count for whether its a plaza point or regular point
def get_booth_count(point):
    if point in PLAZA_POINTS:
        return BOOTHS_PER_PLAZA
    else:
        return BOOTHS_PER_REGULAR

def generate_vehicle_id():
    global vehicles_generated
    
    with vehicle_lock:
        if vehicles_generated >= MAX_VEHICLES:
            return None
        
        vehicle_type = random.choice(VEHICLE_TYPES)
        vehicle_number = str(random.randint(1, 10**VEHICLE_MAX_DIGITS - 1)).zfill(VEHICLE_MAX_DIGITS)
        vehicle_id = f"{vehicle_type}{vehicle_number}"
        
        # incase it created a duplicate vehicle id
        while vehicle_id in generated_vehicles:
            vehicle_number = str(random.randint(1, 10**VEHICLE_MAX_DIGITS - 1)).zfill(VEHICLE_MAX_DIGITS)
            vehicle_id = f"{vehicle_type}{vehicle_number}"
        
        # add to list and counter
        generated_vehicles.add(vehicle_id)
        vehicles_generated += 1
            
        return vehicle_id

def booth_worker(point, booth_id, is_entry):
    global startup_complete

    try:
        if is_entry:
            booth_type = "Entry"
        else:
            booth_type = "Exit"

        point_name = f"Point {point+1}"
        
        print(f"[STARTING] {booth_type} Booth {booth_id} at {point_name}")
        
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect((SERVER_HOST, SERVER_PORT))
        
        # register booth to server
        register_data = {
            "booth_id": booth_id,
            "point": point,
            "is_entry": is_entry
        }
        client_sock.send(json.dumps(register_data).encode())
        
        # register response
        response = json.loads(client_sock.recv(1024).decode())
        if response.get("status") != "Success":
            print(f"[ERROR] Failed to register {booth_type} Booth {booth_id} at {point_name}: {response.get('message')}")
            client_sock.close()
            startup_barrier.wait()  # release barrier even if registration fail
            return
        
        print(f"[REGISTERED] {booth_type} Booth {booth_id} at {point_name}")
        
        startup_barrier.wait()
        time.sleep(0.1)
        
        # main loop
        failures_count = 0
        while running:
            try:
                if is_entry:
                    vehicle_arrival_delay = random.uniform(MIN_ENTRY_DELAY, MAX_ENTRY_DELAY)
                    time.sleep(vehicle_arrival_delay)
                
                    vehicle_id = generate_vehicle_id()
                    
                    # SEND entry request
                    request = {
                        "action": "entry", 
                        "booth_id": booth_id, 
                        "point": point,
                        "vehicle_id": vehicle_id
                    }
                else:
                    time.sleep(random.uniform(3, 10))
                    # exit request
                    request = {
                        "action": "exit",
                        "booth_id": booth_id,
                        "point": point
                    }
                    
                client_sock.send(json.dumps(request).encode())
                
                # GET response
                response = json.loads(client_sock.recv(1024).decode())
                
                if response.get("status") == "Success":
                    failures_count = 0
                    
                    if is_entry:
                        print(f"[ENTRY] {response.get('vehicle_id')} entered at {point_name} Booth {booth_id}")
                    else:
                        print(f"[EXIT] {response.get('vehicle_id')} exited at {point_name} Booth {booth_id}, " 
                              #f"Travel time: {response.get('travel_time', 0):.2f}s, "
                              f"Toll: ${response.get('toll_fee', 0):.2f}")
                    
                    processing_time = random.uniform(1, 2)
                    time.sleep(processing_time)
                elif response.get("status") == "Complete":
                    print(f"[STOPPED] {booth_type} Booth {booth_id} at {point_name} - Simulation complete")
                    client_sock.close()
                    break
                else:
                    failures_count += 1
                    
                    # if operation failed, wait longer before trying again
                    if is_entry:
                        wait_time = min(0.5 * failures_count, 5.0)
                    else:
                        wait_time = random.uniform(1.0, 3.0)
                    
                    time.sleep(wait_time)
                
            except ConnectionResetError:
                print(f"[ERROR] Connection reset for {booth_type} Booth {booth_id} at {point_name}")
                try:
                    client_sock.close()
                    time.sleep(1) 
                    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    client_sock.connect((SERVER_HOST, SERVER_PORT))
                    
                    # re-register
                    client_sock.send(json.dumps(register_data).encode())
                    response = json.loads(client_sock.recv(1024).decode())
                    if response.get("status") != "Success":
                        print(f"[ERROR] Failed to re-register booth: {response.get('message')}")
                        time.sleep(5)
                        continue
                    print(f"[RECONNECTED] {booth_type} Booth {booth_id} at {point_name}")

                except Exception as reconnect_error:
                    print(f"[ERROR] Failed to reconnect {booth_type} Booth {booth_id}: {reconnect_error}")
                    time.sleep(5)
                    continue

            except Exception as e:
                print(f"[ERROR] {booth_type} Booth {booth_id} at {point_name}: {e}")
                time.sleep(1)
                continue

            finally:
                if failures_count >= 5:
                    print(f"[ERROR] {booth_type} Booth {booth_id} at {point_name} - Too many failures, shutting down")
                    client_sock.close()
                    break
        
        # stay connected until the end of the simulation
        if not is_entry:
            try:
                while running:
                    request = {
                        "action": "exit",
                        "booth_id": booth_id,
                        "point": point
                    }
                    
                    client_sock.send(json.dumps(request).encode())
                    
                    # Get response
                    response = json.loads(client_sock.recv(1024).decode())
                    
                    if response.get("status") == "Success":
                        print(f"[EXIT] {response.get('vehicle_id')} exited at {point_name} Booth {booth_id}, " 
                              #f"Travel time: {response.get('travel_time', 0):.2f}s, "
                              f"Toll: ${response.get('toll_fee', 0):.2f}")
                        time.sleep(2)
                    else:
                        time.sleep(3)   

            except Exception as e:
                print(f"[ERROR] {booth_type} Booth {booth_id} at {point_name} exit loop: {e}")
        
    except Exception as e:
        print(f"[FATAL ERROR] {booth_type} Booth {booth_id} at {point_name}: {e}")
        if startup_barrier and not startup_complete:
            try:
                startup_barrier.wait()  # Release the barrier even on error
            except:
                pass

def calculate_total_booths():
    total = 0
    for point in range(TOTAL_POINTS):
        booth_count = get_booth_count(point)
        total += booth_count
    return total

def start_simulation():
    global running, startup_complete, startup_barrier
    running = True
    startup_complete = False
    
    # calculate total booths
    total_booths = calculate_total_booths()
    print(f"Setting up {total_booths} toll booths across {TOTAL_POINTS} points")
    print(f"Vehicle limit set to {MAX_VEHICLES} vehicles")
    
    # synchronize booth startup
    startup_barrier = threading.Barrier(total_booths + 1)  # +1 for main thread
    
    booth_threads = []
    
    # create booths for each point
    for point in range(TOTAL_POINTS):
        is_plaza = point in PLAZA_POINTS
        booth_count = BOOTHS_PER_PLAZA if is_plaza else BOOTHS_PER_REGULAR
        
        # distribute booth categories (entry or exit)
        entry_booths = max(1, booth_count // 2)
        exit_booths = booth_count - entry_booths
        
        # set entry booth threads
        for booth_id in range(1, entry_booths + 1):
            thread = threading.Thread(
                target=booth_worker,
                args=(point, booth_id, True),  # is_entry=True
                daemon=True
            )
            booth_threads.append(thread)
            thread.start()
            time.sleep(0.02)
        
        # set exit booth threads
        for booth_id in range(entry_booths + 1, booth_count + 1):
            thread = threading.Thread(
                target=booth_worker,
                args=(point, booth_id, False),  # is_entry=False
                daemon=True
            )
            booth_threads.append(thread)
            thread.start()
            time.sleep(0.02)
    
    print(f"Started {len(booth_threads)} booth worker threads")
    print("Waiting for all booths to register...")
    
    # wait for all booths to finish
    startup_barrier.wait()
    print("\n----- ALL BOOTHS REGISTERED SUCCESSFULLY -----")
    print("----- STARTING VEHICLE OPERATIONS NOW -----\n")
    
    # allow vehicle operations
    startup_complete = True
    
    try:
        while True:
            time.sleep(1)
                    
    except KeyboardInterrupt:
        print("\nShutting down simulation...")
        running = False
        
        for thread in booth_threads:
            thread.join(timeout=1.0)
        
        print("Simulation stopped")

if __name__ == "__main__":
    start_simulation()