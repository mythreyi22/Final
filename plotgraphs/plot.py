import csv
import os
import shutil
import subprocess as sub
import re
import platform
import time, glob, math
import xlsxwriter
import datetime

try:
    from paths_cfg import my_email_from, my_email_to, my_smtp_pwd, my_smtp_host, my_smtp_port
except ImportError, e:
    print '** `my_email_*` not defined, defaulting to None'
    my_email_from, my_email_to, my_smtp_pwd = None, None, None

csv_files =[]
total_list =[]
video_list =[]
qp_no = 0
hm_fps_list = []
hm_video = []
hm_bitrate_list = []
total_list = []
hm_psnr_list = []
hm_qp_list = []
x264_fps_list = []
x264_video = []
x264_bitrate_list = []
x264_clilist = []
x264_psnr_list = []
x264_qp_list = []
x264=0
    
def write_sheet():
    global group_list
    global csvfile
    global total_list
    global video_list
    global qp_no
    global hm_fps_list
    global hm_bitrate_list
    global hm_psnr_list
    global hm_qp_list
    global hm_ssim_list
    global hm_ssimdB_list
    ram_disk = "No"
    global hm_video
    global sys_info_file
    global x264_fps_list
    global x264_bitrate_list
    global x264_psnr_list
    global x264_qp_list
    global x264_video
    global date_hm
    global date_x264
    global x264_split_next
    global x264_clilist
    global x264_ssimlist
    global x264_ssimdBlist
    global format1
    start =[]
    x264=0
    x264=0
    hm_index = 99
    x264_index = 99
    max_speed = 0
    overall_psnr_max = 0
    overall_fps_max = 0
    i_speed_index = 0
    k_speed_index = 0
    i_psnr_index = 0
    k_psnr_index = 0
    max_fps_mode = ''
    max_psnr_mode = ''
    max_psnr_video_name = ''
    max_fps_video_name = ''
    max_fps_qp = 0
    max_psnr_qp = 0

    quality1 = ["ultrafast(cqp)","superfast(cqp)","fast(crf)","medium(crf)","slow(crf)","veryslow(crf)","ultrafast(ABR)","superfast(ABR)","fast(ABR)","medium(ABR)","slow(ABR)","veryslow(ABR)"] #different x265 presets
    for x in range(0,len(video_list)) :

        max_speed_i_index = 0
        max_speed_k_index = 0
        max_speed_x265 = 0
        max_psnr_x265 = 0
        max_psnr_i_index = 0
        max_psnr_k_index = 0
        max_psnr_mode_x265 = ''
        max_fps_mode_x265 = ''
        max_psnr_video_name_x265 = ''
        max_fps_video_name_x265 = ''
        max_fps_qp_x265 = 0
        max_psnr_qp_x265 = 0
        max_speed = max_psnr = max_bitrate = 0
        min_psnr = 9999
        worksheet = workbook.add_worksheet(video_list[x])
        worksheet.set_zoom(80)
        format = workbook.add_format()
        format.set_bold()
        format.set_align('center')
        format2 = workbook.add_format()
        format2.set_align('center')
        worksheet.insert_image('C1','x265-mcw.png',{'x_offset' : 20})
        row = 3
        col = 1


        for j in range(0,len(hm_video)) :
            if(hm_video[j] == video_list[x]) :
                hm_index = j;
        if hm_index == 99:
            print "HM Reference not found for video :",video_list[x]
        else :
            col = 1
            worksheet.write(row,col-1,'HM 11.0',format)
            worksheet.write(row,col,'CQP',format)
            worksheet.write(row,col+1,'CLI',format)
            worksheet.write(row,col+2,'Speed',format)
            worksheet.write(row,col+3,'Bitrate',format)
            worksheet.write(row,col+4,'vqmt-SSIM',format)
            worksheet.write(row,col+5,'vqmt-SSIM(dB)',format)
            worksheet.write(row,col+6,'Version',format)
            
            hm_qp_count = len(hm_qp_list[hm_index])
            hm_start = row + 1
            worksheet.write(hm_start,0,date_hm,format)

            for l in range(0,len(hm_qp_list[hm_index])) :
             
                row = row + 1
                col = 1
                if not "10bit" in video_list[x] :
                    worksheet.write(row,col,float(hm_qp_list[hm_index][l]),format2)
                    worksheet.write(row,col+2,float(hm_fps_list[hm_index][l]),format2)
                    worksheet.write(row,col+4,float(hm_ssim_list[hm_index][l]),format2)
                    worksheet.write(row,col+5,float(hm_ssimdB_list[hm_index][l]),format2)
                    worksheet.write(row,col+3,float(hm_bitrate_list[hm_index][l]),format2)
                    worksheet.write(row,col+6,str(hm_version_list[hm_index][l]),format2)
                    if float(hm_fps_list[hm_index][l]) > max_speed :
                        max_speed = float(hm_fps_list[hm_index][l])
                    if float(hm_bitrate_list[hm_index][l]) > max_bitrate :
                        max_bitrate = float(hm_bitrate_list[hm_index][l])
        row = row + 2

        for j in range(0,len(x264_video)) :
            if(x264_video[j] == video_list[x]) :
                x264_index = j;
        if x264_index == 99:
            print "x264 values not found for video :",video_list[x]
        else :
                col = 1
                x264_start = row + 1
                worksheet.write(x264_start,0,date_x264,format)
                worksheet.write(row,col-1,'       x264 veryslow(crf)',format)
                worksheet.write(row,col,'CRF',format)
                worksheet.write(row,col+1,'CLI',format)
                worksheet.write(row,col+2,'Speed',format)
                worksheet.write(row,col+3,'Bitrate',format)
                worksheet.write(row,col+4,'vqmt-SSIM',format)
                worksheet.write(row,col+5,'vqmt-SSIM(dB)',format)
                worksheet.write(row,col+6,'Version',format)
                
                x264_qp_count = len(x264_qp_list[x264_index])
                print("qp count",x264_qp_count)
                for l in range(0,len(x264_qp_list[x264_index])) :
                    row = row + 1
                    col = 1
                    x264=x264+1

                    worksheet.write(row,col,float(x264_qp_list[x264_index][l]),format2)
                    worksheet.write(row,col+2,float(x264_fps_list[x264_index][l]),format2)
                    worksheet.write(row,col+3,float(x264_bitrate_list[x264_index][l]),format2)
                    worksheet.write(row,col+1,(x264_clilist[x264_index][l]),format2)
                    worksheet.write(row,col+4,float(x264_ssimlist[x264_index][l]),format2)
                    worksheet.write(row,col+5,float(x264_ssimdBlist[x264_index][l]),format2)
                    worksheet.write(row,col+6,str(x264_versionlist[x264_index][l]),format2)
                    if float(x264_fps_list[x264_index][l]) > max_speed :
                        max_speed = float(x264_fps_list[x264_index][l])
                    if float(x264_bitrate_list[x264_index][l]) > max_bitrate :
                        max_bitrate = float(x264_bitrate_list[x264_index][l])
        
        row = row + 2
        col = 0

        worksheet.write(row,col,"Machine Information",workbook.add_format({'bold': True, 'font_color': 'red'}))
        row = row + 1
        worksheet.write(row,col,"Processor:IntelXeonCPU-E5-2666v3, RAM:58.0, OS:AmazonLinuxAMIrelease201403")
        
        row = row + 2
        col = 0
        build_list = ["Build config : GCC","Build option : 8bpp"]
        worksheet.write(row,col,"Build Information",workbook.add_format({'bold': True, 'font_color': 'red'}))
        row = row + 1
        worksheet.write(row,col,build_list[0]+","+build_list[1])
        col = col + 1
        
        for i in range (0,len(total_list[x])) :
                col = 1
                row = row + 3
                start.append(row + 1)
                print("inside....", len(total_list[x]))
                worksheet.write(row,col-1,quality1[i],format)
                if "cqp" in quality1[i]:
                    worksheet.write(row,col,'CQP',format)
                elif "crf" in quality1[i]:
                    worksheet.write(row,col,'CRF',format)
                else:
                    worksheet.write(row,col,'ABR',format)
                worksheet.write(row,col+1,'CLI',format)
                worksheet.write(row,col+2,'Date/Time',format)
                worksheet.write(row,col+3,'Elapsed Time',format)
                worksheet.write(row,col+4,'Speed',format)
                worksheet.write(row,col+5,'Bitrate',format)
                worksheet.write(row,col+6,'Global PSNR Y',format)
                worksheet.write(row,col+7,'Global PSNR U',format)
                worksheet.write(row,col+8,'Global PSNR V',format)
                worksheet.write(row,col+9,'Global PSNR',format)
                worksheet.write(row,col+10,'vqmt-SSIM',format)
                worksheet.write(row,col+11,'vqmt-SSIM(dB)',format)
                worksheet.write(row,col+12,'Version',format)
                for k in range (0,len(total_list[x][i][0])) :
		  if k < 11 : 
                    row = row + 1
                    col = 2
                    for l in range (0,len(total_list[x][i][k])) :
                        if l == 0:
                            cli_token = total_list[x][i][k][l].split(' ')
                            for f in range (0,len(cli_token)) :
                                if re.match("--crf",cli_token[f]) or re.match("--qp",cli_token[f]):
                                    qp=cli_token[f+1]
                                else:
                                    if re.match("--bitrate",cli_token[f]) or re.match("--bitrate",cli_token[f]):
                                        qp=cli_token[f+1]
			worksheet.write(row,1,int(qp),format2)
                        worksheet.write(row,col,total_list[x][i][k][l],format2)
                        col=col+1

                        if (l==3) and (total_list[x][i][k][l] >max_speed) :
                            max_speed=total_list[x][i][k][l]
                        if (l==3) and (total_list[x][i][k][l] >max_speed_x265) :
                            max_speed_x265=total_list[x][i][k][l]
                            max_speed_i_index=i
                            max_speed_k_index=k
                            max_speed_l_index=x
                            max_fps_mode_x265=quality1[i]
                            max_fps_video_name_x265=video_list[x]
                            max_fps_qp_x265=qp
                        if (l==4) and (total_list[x][i][k][l] >max_bitrate) :
                            max_bitrate=total_list[x][i][k][l]
                        if (l==8) and (total_list[x][i][k][l] >max_psnr) :
                            max_psnr=total_list[x][i][k][l]
                        if (l==8) and (total_list[x][i][k][l] >max_psnr_x265) :
                            max_psnr_x265=total_list[x][i][k][l]
                            max_psnr_i_index=i
                            max_psnr_k_index=k
                            max_psnr_l_index=x
                            max_psnr_mode_x265=quality1[i]
                            max_psnr_video_name_x265=video_list[x]
                            max_psnr_qp_x265=qp
                        if (l==8) and (total_list[x][i][k][l] <min_psnr) :
                            min_psnr=total_list[x][i][k][l]
                        if(max_speed_x265 > overall_fps_max) :
                            overall_fps_max = max_speed_x265
                            i_speed_index = max_speed_i_index
                            k_speed_index = max_speed_k_index
                            l_speed_index = x
                            max_fps_mode = max_fps_mode_x265
                            max_fps_video_name = max_psnr_video_name_x265
                            max_fps_qp = max_fps_qp_x265
                        if(max_psnr_x265 > overall_psnr_max) :
                            overall_psnr_max = max_psnr_x265
                            i_psnr_index = max_psnr_i_index
                            k_psnr_index = max_psnr_k_index
                            video_index = x
                            max_psnr_mode = max_psnr_mode_x265
                            max_psnr_video_name = max_psnr_video_name_x265
                            max_psnr_qp = max_psnr_qp_x265
            
        min_psnr=32
        first_chart = workbook.add_chart({'type': 'scatter'})
        ssim_min=0.92
        ssim=0.8
        diff=0.08
        ssim_max=0.98
        if 'BasketballDrive_1920x1080_50' in video_list[x] :
           ssim_min=0.845
           ssim_max=0.945
           diff=0.02
        if 'Johnny_1280x720_60' in video_list[x] :
           ssim_min=0.94
           ssim_max=0.98
           diff=0.01
        if 'Kimono1_1920x1080_24' in video_list[x] :
           ssim_min=0.89
           ssim_max=0.965
           diff=0.015
        if 'KristenAndSara_1280x720_60' in video_list[x] :
           ssim_min=0.92
           ssim_max=0.98
           diff=0.01
        if 'ParkScene_1920x1080_24' in video_list[x] :
           ssim_min=0.84
           ssim_max=0.96
           diff=0.02
        if 'Traffic_4096x2048_30p' in video_list[x] :
           ssim_min=0.92
           ssim_max=0.98
           diff=0.015
        if 'News_4k' in video_list[x] :
           ssim_min=0.988
           ssim_max=0.996
           diff=0.002
        if 'Coastguard_4k' in video_list[x] :
           ssim_min=0.97
           ssim_max=0.995
           diff=0.005
        if 'tearsofsteel_4k_1000f_s214' in video_list[x] :
           ssim_min=0.82
           ssim_max=0.93
           diff=0.02
           max_bitrate=50000
        if 'sintel_4k_600f' in video_list[x] :
           ssim_min=0.965
           ssim_max=0.99
           diff=0.005
        if 'TOS_4k_1714p_10bit' in video_list[x] :
           ssim_min=0.89
           ssim_max=0.95
           diff=0.01
        if 'ElFuente_4k_2160p_10bit' in video_list[x] :
           ssim_min=0.93
           ssim_max=0.99
           diff=0.01
        if 'sintel_4k_1744p_10bit' in video_list[x] :
           ssim_min=0.96
           ssim_max=0.99
           diff=0.007
            
        
        first_chart.set_x_axis({'name': "Speed(FPS)", 'min': 0, 'max': int(max_speed+1),'color': 'black','num_font':  {'name': 'Calibri','size': 10}})
        first_chart.set_y_axis({'name': "Quality(SSIM)",'min': ssim_min, 'max': ssim_max,'major_unit' : diff,'color': 'black','num_font':  {'name': 'Calibri','size': 10}})
        second_chart = workbook.add_chart({'type': 'scatter'})
        second_chart.set_x_axis({'min': 0, 'max': max_bitrate,'name': ''+"Bit Rate (kbps)",'color': 'black','num_font':  {'name': 'Calibri','size': 10}})
        second_chart.set_y_axis({'min': ssim_min, 'max': ssim_max,'major_unit' : diff,'name': ''+"Quality(SSIM)",'color': 'black','num_font':  {'name': 'Calibri','size': 10}})

        color = ["#A3A300","#00B050","#7030A0","#852400","#0070C0","#E9967A","#008B8B","#C71585","#C0C0C0","#000080","#800000","#808080"]
        type = ["circle","square","circle","square","diamond","triangle","circle","square","triangle","diamond","diamond","square"]
        
        

        val=0
        for i in range(0,len(quality1)) :
            if val>10:
                val=0
            else :
                val=val+1
            first_chart.add_series({'name' : ''+quality1[i],'categories': '='+video_list[x]+'!$F$'+str(start[i]+1)+':$F$'+str(start[i]+qp_no),'values': '='+video_list[x]+'!$L$'+str(start[i]+1)+':$L$'+str(start[i]+qp_no),'line':{'color':color[val],'width': 2.25},'smooth':{'value': True},'data_labels':{'value': False},
            'marker': {'type': type[val],'size': 7,'border': {'color': color[val]},'fill':{'color': color[val]},},},)

            second_chart.add_series({'name' : ''+quality1[i],'categories': '='+video_list[x]+'!$G$'+str(start[i]+1)+':$G$'+str(start[i]+qp_no),'values': '='+video_list[x]+'!$L$'+str(start[i]+1)+':$L$'+str(start[i]+qp_no),'line':{'color':color[val],'width': 2.25},'smooth':{'value': True},'data_labels':{'value': False},
            'marker': {'type': type[val],'size': 7,'border': {'color': color[val]},'fill':{'color': color[val]},},},)
            

            

        first_chart.add_series({'name' : 'x264 veryslow(crf)','categories': '='+video_list[x]+'!$D$'+str(x264_start+1)+':$D$'+str(x264_start+qp_no),'values': '='+video_list[x]+'!$F$'+str(x264_start+1)+':$F$'+str(x264_start+qp_no),'line':{'color':'#808080','width': 1,'dash_type' : 'dash'},'smooth':{'value': True},'data_labels':{'value': False},
        'marker': {'type': 'x','size': 5,'border': {'color': '#808080'},'fill': {'none': True},},},)
        second_chart.add_series({'name' : 'x264 veryslow(crf)','categories': '='+video_list[x]+'!$E$'+str(x264_start+1)+':$E$'+str(x264_start+qp_no),'values': '='+video_list[x]+'!$F$'+str(x264_start+1)+':$F$'+str(x264_start+qp_no),'line':{'color':'#808080','width': 1,'dash_type' : 'dash'},'smooth':{'value': True},'data_labels':{'value': False},
        'marker': {'type': 'x','size': 5,'border': {'color': '#808080'},'fill': {'none': True},},},)

        
        if not '10bit' in video_list[x] :
            first_chart.add_series({'name' : 'HM 11.0','categories': '='+video_list[x]+'!$D$'+str(hm_start+1)+':$D$'+str(hm_start+hm_qp_count),'values': '='+video_list[x]+'!$F$'+str(hm_start+1)+':$F$'+str(hm_start+hm_qp_count),'line':{'color':'#000000','width': 3.00},'smooth':{'value': True},'data_labels':{'value': False},
            'marker': {'type': 'square','size': 7,'border': {'color': '#000000'},'fill':{'color': '#000000'},},},)
            second_chart.add_series({'name' : 'HM 11.0','categories': '='+video_list[x]+'!$E$'+str(hm_start+1)+':$E$'+str(hm_start+hm_qp_count),'values': '='+video_list[x]+'!$F$'+str(hm_start+1)+':$F$'+str(hm_start+hm_qp_count),'line':{'color':'#000000','width': 3.00},'smooth':{'value': True},'data_labels':{'value': False},
            'marker': {'type': 'square','size': 7,'border': {'color': '#000000'},'fill':{'color': '#000000'},},},)
            


        first_chart.set_size({'width' : 768, 'height' : 528})
        first_chart.set_legend({'position' : 'bottom'})
        first_chart.set_chartarea({'border': {'color':'black'},'fill':   {'color': 'white'}})
        worksheet.insert_chart('W1', first_chart,{ 'x_offset' : 0})
        
        second_chart.set_size({'width' : 768, 'height' : 528})
        second_chart.set_legend({'position' : 'bottom'})
        second_chart.set_chartarea({'border': {'color':'black'},'fill':   {'color': 'white'}})
        worksheet.insert_chart('K1', second_chart)

        worksheet.hide_gridlines(2)

def csv_extract_val() :
    print("inside of csv_extract values")
    print csv_files
    f1 = open(csv_files, 'rU')
    global qp_no
    global video_list
    global total_list
    global curr_dir
    mainprofile="false"
    video_flag = 0
    group_list = []
    minilist = []
    qp_count = 1
    first = 0
    line = f1.readline()
    line = f1.readline()
    while line :
        next = f1.readline()
        cells = line.split(",")
        cells1 = next.split(",")
        cli_parse = cells[0].split(' ')
        next_parse = cells1[0].split(' ')
        output = []
        temp = cells[0]
        if temp[:7] == " --psnr":
            print 'extracting csv files'
        else:
            break;

        for file in glob.glob("..//AutomatedTest//decodedfiles//*.csv"):
	    if file.split("/")[-1].replace(".yuv_ssim","").replace(".csv","") in cells[0]:
		with open(file, 'r') as readfile:
                    for line in readfile:
                      if line.startswith('average'):
                             line_split=line.split(',')
                             SSIM=line_split[1]
                             inv_SSIM=1-float(SSIM)
                             SSIMdb=-10 * math.log(inv_SSIM, 10)
                             SSIMdb=round(SSIMdb,3)
                             mainprofile="true"
        
        #append all the values from the csv file to list
        output.append(cells[0])
        output.append(cells[1])
        output.append(float(cells[2]))
        output.append(float(cells[3]))
        output.append(float(cells[4]))
        output.append(float(cells[5]))
        output.append(float(cells[6]))
        output.append(float(cells[7]))
        output.append(float(cells[8]))
        if mainprofile=="true":
            output.append(float(SSIM))
            output.append(float(SSIMdb))
            mainprofile="false"
        else:
            output.append(float(cells[9]))
            output.append(float(cells[10].replace('dB','')))
        if len(cells) > 15:
            output.append(cells[32])
        else:
            output.append(cells[11])
        minilist.append(output)
        for i in range (0,len(cli_parse)) :
            if cli_parse[i].endswith('y4m') or cli_parse[i].endswith('yuv') :
                break;
        for x in range(0,len(next_parse)) :
            if next_parse[x].endswith('y4m')  or next_parse[x].endswith('yuv') :
                break;
        if (cli_parse[i].replace("_--preset","") == next_parse[x].replace("_--preset","") and len(cells1) > 1) :                   #check if cli matches
            for i in range (0,len(cli_parse)) :
                if re.search('preset',cli_parse[i].replace("_--preset",""))  :
                    break;
            for x in range(0,len(next_parse)) :
                if re.search('preset',next_parse[x].replace("_--preset","")) :
                    break;
            if (cli_parse[i+1] == next_parse[x+1] and len(cells1) > 1) :
                qp_count = qp_count+1
            else :
                if first :
                    qp_no = qp_count                                              #store qp count
                group_list.append(minilist)         #list which has all values of the particular preset 
                qp_count = 1
                first = 1
                minilist = []
        else:
            group_list.append(minilist)
            qp_count = 1
            first = 1
            minilist = []
            total_list.append(group_list)                                         #list which has all the preset values of a particular video
            group_list = []
            for j in range(0,len(video_list)) :
                    if cli_parse[i][3:].replace('.y4m','').replace('.yuv','')==video_list[j] :
                        video_flag = 1
            if video_flag == 0 :
                    video_name = cli_parse[i][28:].replace('.y4m','').replace('.yuv','')
                    video_list.append(video_name)                    #add video name to the list
                    print("video list in csv extract",video_list)
            
        video_flag = 0
        line = next
    f1.close()

def hm_extract_val() :
    print("in hm extraction loop")
    global hm_fps_list
    global hm_bitrate_list
    global hm_psnr_list
    global hm_qp_list
    global hm_ssim_list
    global hm_ssimdB_list
    global hm_version_list
    global hm_video
    global hm_dbitrate
    global hm_dpsnr
    global hm_dvideo
    global csv_files 
 
    
    hm_dvideo=[]
    hm_dbitrate=[]
    hm_dpsnr=[]    
    hm_qp_count = 1
    hm_video_flag = 0
    hm_line = 0
    hm_first = 0
    hm_bitrate_minilist = []
    hm_fps_minilist = []
    hm_psnr_minilist = []
    hm_qp_minilist = []
    hm_ssim_list = []
    hm_ssimdB_list = []
    hm_version_list = []
    hm_version_minilist = []
    hm_ssim_minilist = []
    hm_ssimdB_minilist = []
    global date_hm
    file = csv_files.replace("x265Benchmark","hm")
    
    for f in os.listdir(".") :
        #print(f,file)
        if re.search(file,f) :
            hm_f = open(f,'rU')
            
            date_hm = '11-8-14'
            flag = 1
            hm_l = hm_f.readline()
            hm_l = hm_f.readline()                                               #first line of the x264 csv file
    if flag==0 :
        print "HM file for " +csv_files+" not found"
        hm_l = 0
    while hm_l :
             
             hm_n = hm_f.readline()                                              #Next line of the x264 file
             hm_split = hm_l.split(',') 
             hm_split_next = hm_n.split(',')  
             hm_cli = hm_split[0].split(' ')                                     #separate CLI alone from the line
             hm_cli1 = hm_split_next[0].split(' ')
             #append fps,bitrate,psnr values of the line to the list
             hm_fps_minilist.append((hm_split[1]))
             hm_ssim_minilist.append((hm_split[3]))
             hm_ssimdB_minilist.append((hm_split[4]))
             hm_bitrate_minilist.append((hm_split[2]))
             hm_version_minilist.append((hm_split[5]))
             hm_dvideo.append((hm_split[0]))
             hm_dbitrate.append((hm_split[2]))
             
             for i in range (0,len(hm_cli)) :
                 if hm_cli[i].endswith('y4m') or hm_cli[i].endswith('yuv') :
                     hm_l_video = hm_cli[i].replace('.y4m','').replace('.yuv','')
                     print("hm_l_video is", hm_l_video)
                 if re.search("-q",hm_cli[i]) :                                  #add qp to the list from the CLI
                        hm_qp_minilist.append(str(hm_cli[i+1])) ####CHANGE TO i+1 for new hm files
             for j in range (0,len(hm_cli1)) :
                 if hm_cli1[j].endswith('y4m') or hm_cli1[j].endswith('yuv') :
                     hm_n_video = hm_cli1[j].replace('.y4m','').replace('.yuv','')
             if(hm_l_video == hm_n_video and len(hm_cli1) > 1) :                 #increase qp count if video names are same
                 hm_qp_count = hm_qp_count+1
             else :
                #add video specific minilist to a list
                hm_fps_list.append(hm_fps_minilist)
                hm_bitrate_list.append(hm_bitrate_minilist)
                hm_psnr_list.append(hm_psnr_minilist)
                hm_qp_list.append(hm_qp_minilist)
                hm_ssim_list.append(hm_ssim_minilist)
                hm_ssimdB_list.append(hm_ssimdB_minilist)
                hm_version_list.append(hm_version_minilist)
                hm_psnr_minilist = []
                hm_qp_minilist = []
                hm_bitrate_minilist = []
                hm_ssim_minilist = []
                hm_ssimdB_minilist = []
                hm_version_minilist = []
                hm_fps_minilist =[]
                hm_qp_count = 1
             
             #append video name to the list
             for k in range (0,len(hm_video)) :
                 if hm_l_video == hm_video[k] :
                     hm_video_flag = 1
             if hm_video_flag == 0:
                 hm_video.append(hm_l_video)
                 print("hm_video append", hm_video)
             hm_video_flag = 0
             hm_l = hm_n
             hm_line = hm_line+1
    hm_f.close()

def x264_extract_val() :
    global x264_fps_list
    global x264_bitrate_list
    global x264_psnr_list
    global x264_qp_list
    global x264_video
    global x264_split_next
    global x264_ssimlist
    global x264_ssimdBlist
    global x264_clilist
    global x264_versionlist

    x264_ssimlist = []
    x264_ssimdBlist = []
    x264_versionlist = []
    x264_qp_count = 1
    x264_video_flag = 0
    x264_line = 0
    x264_first = 0
    x264_bitrate_minilist = []
    x264_fps_minilist = []
    x264_psnr_minilist = []
    x264_qp_minilist = []
    x264_clilist_minilist = []
    x264_ssimlist_minilist = []
    x264_ssimdBlist_minilist = []
    x264_versionlist_minilist = []
    global date_x264
    file = csv_files.replace("x265Benchmark","x264")
    print file
    for f in os.listdir(".") :
        print(f,file)
        if re.search(file,f) :
            print f
            x264_f = open(f,'rU')
            date_x264 = '11-8-14'
            flag =1
            x264_l = x264_f.readline()
            x264_l = x264_f.readline()
            print x264_l
    if flag==0 :
        print "X264 file for " +csv_files+" not found"
        x264_l = 0

    while x264_l :
             x264_n = x264_f.readline()                                           
             x264_split = x264_l.split(',') 
             x264_split_next = x264_n.split(',')
             x264_cli = x264_split[0].split(' ')                                  
             x264_cli_next = x264_split_next[0].split(' ')
             x264_fps_minilist.append((x264_split[1]))                          
             x264_bitrate_minilist.append((x264_split[2]))
             x264_clilist_minilist.append((x264_split[0]))
             x264_ssimlist_minilist.append((x264_split[3]))
             x264_ssimdBlist_minilist.append((x264_split[4]))
             x264_versionlist_minilist.append((x264_split[5]))
             for i in range (0,len(x264_cli)) :
                 if x264_cli[i].endswith('y4m') or x264_cli[i].endswith('yuv') :
                     x264_l_video = x264_cli[i].replace('.y4m','').replace('.yuv','') 
               
                 if re.search("--crf",x264_cli[i]) :
                        x264_qp_minilist.append(str(x264_cli[i+1]))             
             for j in range (0,len(x264_cli_next)) :
                 if x264_cli_next[j].endswith('y4m') or x264_cli_next[j].endswith('yuv') :
                     x264_n_video = x264_cli_next[j].replace('.y4m','').replace('.yuv','')
                
             if(x264_l_video == x264_n_video and len(x264_cli_next) > 1) :          
                 x264_qp_count = x264_qp_count+1
             else :
                
                x264_fps_list.append(x264_fps_minilist)                         
                x264_bitrate_list.append(x264_bitrate_minilist)
                x264_clilist.append(x264_clilist_minilist)
                x264_ssimlist.append(x264_ssimlist_minilist)
                x264_ssimdBlist.append(x264_ssimdBlist_minilist)
                x264_psnr_list.append(x264_psnr_minilist)
                x264_qp_list.append(x264_qp_minilist)
                x264_versionlist.append(x264_versionlist_minilist)
                x264_psnr_minilist = []
                x264_qp_minilist = []
                x264_bitrate_minilist = []
                x264_clilist_minilist = []
                x264_ssimlist_minilist = []
                x264_ssimdBlist_minilist = []
                x264_versionlist_minilist = []
                x264_fps_minilist = []
                x264_qp_count = 1
             
             for k in range (0,len(x264_video)) :
                 if x264_l_video == x264_video[k] :
                     x264_video_flag = 1
             if x264_video_flag == 0:
                 x264_video.append(x264_l_video)
                 print("hm_video append", x264_video)
             x264_video_flag = 0
             x264_l = x264_n
             x264_line = x264_line+1

def email():
    if not (my_email_from and my_email_to and my_smtp_pwd):
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.MIMEMultipart import MIMEMultipart
    from email.encoders import encode_base64
    from email.mime.image import MIMEImage

    
    msg = MIMEMultipart()
    for xlfile in glob.glob("*.xlsx") :
        text = MIMEImage(open(xlfile, 'rb').read(), _subtype="xlsx")
        text.add_header('Content-Disposition', 'attachment', filename='x265_PerformanceBenchMarks.xlsx')
    msg.attach(text)
    if type(my_email_to) is str:
        msg['To'] = my_email_to
    else:
        msg['To'] = ", ".join(my_email_to)
    
    msg['From'] = my_email_from
    currentdate=datetime.date.today()
    msg['Subject'] = str(currentdate)+' AWS Test Results'
    
    session = smtplib.SMTP(my_smtp_host, my_smtp_port)
    try:
        session.ehlo()
        session.starttls()
        session.ehlo()
        session.login(my_email_from, my_smtp_pwd.decode('base64'))
        session.sendmail(my_email_from, my_email_to, msg.as_string())
    except smtplib.SMTPException, e:
        print 'Unable to send email', e
    finally:
        session.quit()
    


def main():
    global csv_files
    global workbook
    qp_no = 0
    video_list = []
    total_list = []
    hm_fps_list = []
    hm_video = []
    hm_bitrate_list = []
    total_list = []
    hm_psnr_list = []
    hm_qp_list = []
    x264_fps_list = []
    x264_video = []
    x264_bitrate_list = []
    x264_clilist = []
    x264_psnr_list = []
    x264_qp_list = []
    csv_files = [f for f in os.listdir('.') if f.endswith('.csv')]
    for i in range(0,len(csv_files)) :
        if(re.search("hm_",csv_files[i]) or re.search("x264",csv_files[i])) :
            continue
    csv_files = csv_files[i]
    print csv_files
    x264_extract_val()
    hm_extract_val()
    csv_extract_val()
    workbook = xlsxwriter.Workbook('x265_PerformanceBenchMarks.xlsx')
    write_sheet()
    format = workbook.add_format({'bold': True, 'font_color': 'black'})
    format1 = workbook.add_format({'bold': True, 'font_color': 'red'})
    workbook.close()
    email()

if __name__ == "__main__":
    main()
