import numpy as np
from datetime import datetime
import asyncio, asyncpg #, sys, os

def assembly_data(conn_info=[], ass_type = '', geometry= '', resolution= '', base_layer_id = '', top_layer_id = '', bl_position=None, tl_position=None, put_position=None, region = None, ass_tray_id= '', comp_tray_id= '', put_id= '', ass_run_date= '', ass_time_begin= '', ass_time_end= '', operator= '', tape_batch = None, glue_batch = None, stack_name = 'test', adhesive = None, comments = None):
    if (len(str(base_layer_id)) != 0) and (len(str(top_layer_id)) != 0):  ### dummy runs don't get saved
        try:
            ass_run_date = datetime.strptime(ass_run_date, '%Y-%m-%d')
        except:
            ass_run_date = datetime.now().date()
        
        try:
            ass_time_begin = datetime.strptime(ass_time_begin, '%H:%M:%S')
            ass_time_end = datetime.strptime(ass_time_end, '%H:%M:%S')
        except:
            ass_time_begin = datetime.now().time()
            ass_time_end = datetime.now().time()
        
        inst_code_dict = {'CM':'CMU', 'SB':'UCSB','IH':'IHEP', 'NT':'NTU', 'TI':'TIFR', 'TT':'TTU'}
        sensor_thickness_dict = {'1': 120, '2': 200, '3': 300}
        bp_material_dict = {'W': 'CuW', 'P': 'PCB', 'T': 'Titanium', 'C': 'Carbon fiber'}
        roc_version_dict = {'X': 'preseries'}
        
        pos_col, pos_row = get_col_row(int(bl_position))
        
        db_upload = {'geometry' : geometry, 
                    'resolution': resolution, 
                    'ass_run_date': ass_run_date, 
                    'ass_time_begin': ass_time_begin, 
                    'ass_time_end': ass_time_end, 
                    'pos_col': pos_col,
                    'pos_row': pos_row,
                    'adhesive': adhesive,
                    'operator': operator,
                    'comment': comments,}
        if ass_type == 'proto':
            db_table_name = 'proto_assembly'
            db_upload.update({
                    'proto_name': stack_name, 
                    'bp_name': base_layer_id, 
                    'sen_name': top_layer_id, 
                    'bp_position': str(bl_position), 
                    'sen_position': str(tl_position), 
                    'put_position': str(put_position), 
                    'region': str(region), 
                    'ass_tray_id': str(ass_tray_id), 
                    'sen_tray_id': str(comp_tray_id), 
                    'sen_put_id': str(put_id), 
                    'tape_batch': tape_batch, 
                    'glue_batch': glue_batch})
            db_table_name_list, db_upload_list = db_table_name, db_upload
        elif ass_type == 'module':
            db_table_name = 'module_assembly'
            db_upload.update({
                    'module_name': stack_name, 
                    'proto_name': base_layer_id, 
                    'hxb_name': top_layer_id, 
                    'pml_position': str(bl_position), 
                    'hxb_position': str(tl_position), 
                    'put_position': str(put_position), 
                    'region': str(region), 
                    'ass_tray_id': str(ass_tray_id), 
                    'hxb_tray_id': str(comp_tray_id), 
                    'hxb_put_id': str(put_id), 
                    'tape_batch': tape_batch, 
                    'glue_batch': glue_batch})
            db_upload_info = {'module_name': stack_name, 
                              'proto_name': base_layer_id, 
                             'hxb_name': top_layer_id, 
                            'geometry' : geometry, 
                            'resolution': resolution,
                            'assembled': ass_run_date}
            try:
                db_upload_info.update({'bp_material': bp_material_dict[stack_name[9]],
                                    'sen_thickness': sensor_thickness_dict[stack_name[8]],
                                    'institution': inst_code_dict[stack_name[12:14]],   
                                    'roc_version': roc_version_dict[stack_name[10]]})
            except: print('Check module name again. Code incomplete.')
            db_table_name_list, db_upload_list = [db_table_name, 'module_info'], [db_upload, db_upload_info]
        try:
            return asyncio.run(upload_PostgreSQL(conn_info, db_table_name_list, db_upload_list))
        except:
            return (asyncio.get_event_loop()).run_until_complete(upload_PostgreSQL(conn_info, db_table_name_list, db_upload_list))
    return "Dummy run. Data not saved."

###################################################################################
################################# UPLOAD TO DATABASE ###############################
#################################################################################
def get_query_write(table_name, column_names):
    pre_query = f""" INSERT INTO {table_name} ({', '.join(column_names)}) VALUES """
    data_placeholder = ', '.join(['${}'.format(i) for i in range(1, len(column_names)+1)])
    query = f"""{pre_query} {'({})'.format(data_placeholder)}"""
    return query

async def upload_PostgreSQL(conn_info, table_name_list, db_upload_data_list):
    conn = await asyncpg.connect(
        host=conn_info[0],
        database=conn_info[1],
        user=conn_info[2],
        password=conn_info[3])
    print('Connection successful. \n')
    if type(table_name_list) is not list: table_name_list = [table_name_list]
    if type(db_upload_data_list) is not list: db_upload_data_list = [db_upload_data_list]
    
    schema_name = 'public'
    table_exists_query = """
    SELECT EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = $1 
        AND table_name = $2
    );"""
    
    for table_name, db_upload_data in zip(table_name_list, db_upload_data_list):
        table_exists = await conn.fetchval(table_exists_query, schema_name, table_name)  ### Returns True/False
        if table_exists:
            query = get_query_write(table_name, db_upload_data.keys())
            await conn.execute(query, *db_upload_data.values())
            print(f'Executing query: {query}')
            print(f'Data successfully uploaded to the {table_name}!')
        else:
            print(f'Table {table_name} does not exist in the database.')
    await conn.close()
    return 'Upload Success'

######################################################################################
######################### READ FROM DATABASE ########################################
#######################################################################################
comptable = {'baseplate':{'prefix': 'bp'},'hexaboard':{'prefix': 'hxb'},'protomodule':{'prefix': 'proto'},'module':{'prefix': 'module'}}
def get_query_read(component_type, part_name = None, comptable=comptable):
    if part_name is None:
        query = f"""SELECT {comptable[component_type]['prefix']}_name FROM {comptable[component_type]['prefix']}_inspect ORDER BY {comptable[component_type]['prefix']}_row_no DESC LIMIT 10;"""
    else:
        query = f"""SELECT hexplot FROM {comptable[component_type]['prefix']}_inspect WHERE {comptable[component_type]['prefix']}_name = '{part_name}'"""
    return query


async def fetch_PostgreSQL(conn_info, component_type, bp_name = None):
    conn = ''
    result = await conn.fetch(get_query_read(component_type, bp_name ))
    await conn.close()
    return result

async def find_largest_suffix(conn_info, prefix, table_name = 'proto_assembly', col_name = 'proto_name'):  ####### For getting protomodule count suffix based on type
    conn = await asyncpg.connect(host=conn_info[0], database=conn_info[1], user=conn_info[2], password=conn_info[3])
    query = f"""
        SELECT MAX(CAST(RIGHT({col_name}, 4) AS INTEGER))
        FROM {table_name} 
        WHERE {col_name} LIKE $1"""
    largest_suffix = await conn.fetchval(query, f'{prefix}%')
    await conn.close()
    if largest_suffix == None: largest_suffix = '0';
    print('New suffix:', str(int(largest_suffix)+1).zfill(4))
    return str(int(largest_suffix)+1).zfill(4)
   
def get_number_for_type(conn_info, prefix):
    try:
        try:
            return asyncio.run(find_largest_suffix(conn_info, prefix))
        except:
            return (asyncio.get_event_loop()).run_until_complete(find_largest_suffix(conn_info, prefix))
    except:
        return '9009'
    
def get_col_row(i):
    col, row = 1+(i-1)//2, 1+(i-1)%2
    return col, row

##########################################################################
############################# DEBUGGING TOOLS ################################
#########################################################################

############ OTHER STUFF #######

def debugprint(test=[], news=''):
    return test[2]
#print((cmd_debugger()))

def cmd_debugger(conn_info=[]):
    ass_type, base_layer_id, top_layer_id = 'proto', 'BA_123_test', 'SL_123_test'
    ass_type, base_layer_id, top_layer_id = 'module', 'PL_123_test', 'HB_123_test'
    geometry, resolution = 'Full', 'LD'
    bl_position, tl_position, put_position, region = 1, 1, 1, 1
    ass_tray_id, comp_tray_id, put_id = '1', 2, 1
    ass_run_date = '2012-07-04'
    ass_time_begin = '12:01:00.123'
    ass_time_end = '12:03:59.456'
    tape_batch, glue_batch = None, None
    t = assembly_data(conn_info, ass_type, geometry, resolution, base_layer_id, top_layer_id, str(bl_position), str(tl_position))
    print(t)
    
def db_conn_debugger(conn_info=[]):
    try:
        try:
            conn = asyncio.run(asyncpg.connect(
                host=conn_info[0],
                database=conn_info[1],
                user=conn_info[2],
                password=conn_info[3]))
            return "Connection successful! (Py 3.7)"
        except:
            conn = (asyncio.get_event_loop()).run_until_complete(asyncpg.connect(
                host=conn_info[0],
                database=conn_info[1],
                user=conn_info[2],
                password=conn_info[3]))
            return "Connection successful! (Py 3.6)"
    except:
        return "Connection failed!"

if __name__ == "__main__":
    import os
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    conn_file_path = os.path.join(current_script_dir, "..", "..", "Assembly Data", "Database Config", "conn.txt")
    conn_file_path = os.path.normpath(conn_file_path)

    with open(conn_file_path, 'r') as file:
        conn_info = [line.strip() for line in file]
        
    print("Connection info:", conn_info)
    conn_message = db_conn_debugger(conn_info)
    print(conn_message)
    # print(cmd_debugger(conn_info))
    

