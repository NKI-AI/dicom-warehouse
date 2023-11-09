# DICOM-Warehouse 
_A tool to ease working with large breast MR DICOM databases for deep learning._

--------------------------------------------------------------------------------
**Introduction:**
Deep learning (DL) is nowadays showing its superior performance in image vision tasks like detection and segmentation, 
and it is also entering breast radiology. Unarguably one of the most important factors for a good working DL model is 
the size and quality of the input data. In breast magnetic resonance imaging (MRI), datasets are small, resulting in DL 
models with generally poor generalizability. This can partly be attributed to the DICOM standard, the de facto medical 
image file format for MR, which is hard to work with for large databases: it is very time-consuming to search and select 
the appropriate scans, due to having to open every DICOM file and read its information in the tags; tags can have manual
input, these unstandardized tags make searching and selecting undoable; 3D MR scans are split into many 2D DICOM files,
loading these during training of a DL network is too slow. To overcome these problems, and enable the easy creation of 
large MR datasets for DL research, open-source software is needed. And that is why there is now the DICOM-Warehouse.

**Methods:**
The DICOM-Warehouse makes it possible to handle large DICOM databases. It _first reads in the header of all your DICOM 
files to an SQL database_ of your choice. Conveniently, all relevant tags of the headers are already selected, so that no
important information is missed, and no unuseful data is stored. However, if you need a specific tag for your research,
adjusting the tags is a matter of seconds. Secondly, the _modality of all imported series is determined_ based on the 
saved tags in the database, making a distinction between T1, T2 or DWI as easy as can be. Thirdly, the DICOM-Warehouse 
can _transform your DICOM files into 3D file formats_. These 3D files are perfect formats to be directly used for DL 
training, and when creating these with the DICOM-Warehouse, you will only have to do this once. Fourthly, the database 
can be easily queried, and accordingly, *manifest files can be created* based upon these queries. These manifest are 
tailor-made, including the possibility of adding relevant information for your research specifically. Lastly, in your
research the DICOM files will be most likely be accompanied by some Excel/csv file containing data about scans, 
for example which ones contain malignancies. The DICOM-Warehouse makes it _easy to 
integrate this data perfectly in the same database_!

-------------------------------
**Elaborate methods:**
The following six stages will be explained in more detail.

0. Set up SQL database.
1. Import DICOM headers into SQL database.
2. Extract MR modalities and study-protocol based on (non-human-input) tags.
3. Export series from DICOM header to 3D file format.
4. Import own data (non-DICOM) into SQL database.
5. Query database / generate manifest files.


(0) Set up your database before using the DICOM-Warehouse. Currently, the software is capable of connecting to 
SQLite and PostgreSQL databases. Make sure you point the DICOM-Warehouse to the right database by changing the 
contents in `config/database.ini`. Be aware: You don't have to create the tables yourself, only initializing the
SQL database is enough. For SQLite, there is not even a need to create the database beforehand, this one will be 
automatically created.

(1) In order to start the import of DICOM files into an SQL database, use `dcmw.dicom_to_database`. By using the flag 
`--dirs`, the software will import all DICOM files contained in these folders (and their sub-folders). In order to use
multiprocessing, use `--threads` to indicate the amount of available workers. The headers will be read into the database
 according to the DICOM Standard structure: Patient - Study - Series - Image. However, in addition to these tables, 
there will also be tables specifically for MRIImage and multiple MRI vendor specific tables (for now Philips, Siemens, 
and GE). For convenience and data storage, only relevant tags will be read in, however, if you are in the need of a 
specific tag which is not included, you can change the contents of `config/config.toml` to include tags of your choice.

(2) In order to extract MR modalities of series and the full breast MR study protocol, use `dcmw.modality_extraction`. 
Again, multiprocessing can be enabled by using the `--threads` flag. The modalities will be extracted based upon the 
tags in table Series, Image and MRIImage and vendor specific logic. Examples of modalities are 'T1 Weighted', 
'T2 Weighted' and 'DWI'. Every modality has different subtypes. For example, 'DWI' modality has a subtype either 'ADC' 
or 'DWI', which will be accompanied by the corresponding b-values. Each modality will have their own designated table in 
the database, as well as the study protocol.

(3) To export the DICOM files to a 3D file format (for now either 'nrrd' or 'nifti'), use `dcmw.dicom_to_scan`. Again, 
multiprocessing can be enabled by using the `--threads` flag. Don't forget to set the `--save_dir` flag to point the 
DICOM-Warehouse to the right location to store the created 3D scans. In the database, a new table will be created, 
called 'scan_path', containing the file locations. Be aware that a series with different timestamps, like the ultrafast 
series, will be split into multiple 3D scans. Generally, files will be stored as follows: 
`save_dir/patient_name/study_instance_uid/series_instance_uid/time_stamp.{file_format}`.

(4) In order to import your own non-DICOM data to the database, use `dcmw.user_specific_upload`. For now, only .csv and 
Excel file formats are accepted. For every newly added csv or Excel file, a new database table needs to be created. 
Check out `dcmw/models/user_specific_models.py` for a detailed explanation on how to add these models. Don't forget to 
run a migration afterwards! 

(5) Lastly, manifests can easily be generated by using `dcmw.manifest_maker`. This will be created based upon a 
query to the database. As queries are user specific, you will 
need to add your own query to `dcmw/manifest/manifest_query.py`. There are multiple examples in this file which will 
guide you in the right direction. The manifest will be a list of dictionaries, saved in .json format. Each dictionary 
holds the same tags for every series in the query. For convenience, the most important tags are already selected. If 
you wish to change/add some of these tags, have a look at `config/query.toml`. 

![image](https://user-images.githubusercontent.com/50020718/223116085-10ec23b3-6a16-4393-8da7-a588a001782b.png)

_Some stuff about license? Contact information? Better image?_

# TODO: rsyncanator, resampling
#  These are some preprocessing files in the dicom pipeline between DICOM-Warehouse and DL training.
#  Own tables: annotations, more?