#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import shutil
import pytest
import json
import time
import csv
import multiprocessing
from Bio import SeqIO
from Bio import Entrez
from basicfunctions import HelperFunctions as H
from basicfunctions import GeneralFunctions as G
from basicfunctions import ParallelFunctions as P
from strainprimer import SingletonPrimerDesign
from strainprimer import SingletonSummary
from strainprimer import SingletonPrimerQualityControl

msg = (
    """
    Works only in the Docker container!!!
    - Start the container
        sudo docker start {Containername}
    - Start an interactive terminal in the container
        sudo docker exec -it {Containername} bash
    - Start the tests in the container terminal
        cd /
        pytest -vv --cov=/pipeline /tests
    """)


# /tests
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
pipe_dir = os.path.join(BASE_PATH.split("tests")[0], "pipeline")
dict_path = os.path.join(pipe_dir, "dictionaries")
tmpdir = os.path.join("/", "primerdesign", "tmp")
dbpath = os.path.join(tmpdir, "customdb.fas")
testfiles_dir = os.path.join(BASE_PATH, "testfiles")
ref_data = os.path.join(BASE_PATH, "testfiles", "ref")
testdir = os.path.join("/", "primerdesign", "test")

confargs = {
    "ignore_qc": False, "mfethreshold": 90, "maxsize": 200,
    "target": "Lactobacillus_curvatus", "nolist": False, "skip_tree": False,
    "blastseqs": 1000, "mfold": -3.0, "mpprimer": -3.5,
    "offline": False,
    "path": os.path.join("/", "primerdesign", "test"),
    "probe": False, "exception": [], "minsize": 70, "skip_download": True,
    "customdb": dbpath, "assemblylevel": ["all"], "qc_gene": ["rRNA"],
    "virus": False, "genbank": False, "intermediate": True,
    "nontargetlist": ["Lactobacillus sakei"],
    "evalue": 10, "nuc_identity": 0, "runmode": ["strain"], "strains": [],
    "subgroup": []}


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


@pytest.fixture
def config():
    from speciesprimer import CLIconf
    args = AttrDict(confargs)
    nontargetlist = H.create_non_target_list(args.target)
    config = CLIconf(
            args.minsize, args.maxsize, args.mpprimer, args.exception,
            args.target, args.path, args.intermediate,
            args.qc_gene, args.mfold, args.skip_download,
            args.assemblylevel, nontargetlist,
            args.skip_tree, args.nolist, args.offline,
            args.ignore_qc, args.mfethreshold, args.customdb,
            args.blastseqs, args.probe, args.virus, args.genbank,
            args.evalue, args.nuc_identity, args.runmode,
            args.strains, args.subgroup)

    config.save_config()

    return config


def test_start():
    if os.path.isdir(testdir):
        shutil.rmtree(testdir)

    def dbinputfiles():
        filenames = [
            "GCF_004088235v1_20191001.fna",
            "GCF_002224565.1_ASM222456v1_genomic.fna"]
        with open(dbpath, "w") as f:
            for filename in filenames:
                filepath = os.path.join(testfiles_dir, filename)
                records = SeqIO.parse(filepath, "fasta")
                for record in records:
                    if record.id == record.description:
                        description = (
                            record.id +
                            " Lactobacillus curvatus strain SRCM103465")
                        record.description = description
                    SeqIO.write(record, f, "fasta")
            mockseqs = os.path.join(testfiles_dir, "mocktemplate.seqs")
            records = list(SeqIO.parse(mockseqs, "fasta"))
            SeqIO.write(records, f, "fasta")

        return dbpath

    def create_customblastdb():
        cmd = [
            "makeblastdb", "-in", dbpath, "-parse_seqids", "-title",
            "mockconservedDB", "-dbtype", "nucl", "-out", dbpath]
        G.run_subprocess(
            cmd, printcmd=False, logcmd=False, printoption=False)

    if os.path.isdir(os.path.dirname(dbpath)):
        shutil.rmtree(os.path.dirname(dbpath))
    test =  os.path.join("/", "primerdesign", "test")
    if os.path.isdir(test):
        shutil.rmtree(test)

    G.create_directory(os.path.dirname(dbpath))
    dbinputfiles()
    create_customblastdb()


def test_skip_pangenome_analysis(config):
    from speciesprimer import PangenomeAnalysis
    PA = PangenomeAnalysis(config)
    G.create_directory(PA.pangenome_dir)
    fromfile = os.path.join(testfiles_dir, "gene_presence_absence.csv")
    tofile = os.path.join(PA.pangenome_dir, "gene_presence_absence.csv")
    if os.path.isfile(tofile):
        os.remove(tofile)
    shutil.copy(fromfile, tofile)
    exitstat = PA.run_pangenome_analysis()
    assert exitstat == 2


def test_Singleton(config):
    from strainprimer import Singletons
    SI = Singletons(config)

    def prepare_tests():
        if os.path.isdir(SI.ffn_dir):
            shutil.rmtree(SI.ffn_dir)
        new_ffn_dir = os.path.join(testfiles_dir, "ffn_files")
        shutil.copytree(new_ffn_dir, SI.ffn_dir)
        G.create_directory(SI.fna_dir)
#        filenames = os.listdir(SI.ffn_dir)
        filenames =  [
            "GCF_001698165v1_20190923.ffn", "GCF_001435495v1_20190923.ffn",
            "GCF_003254785v1_20190923.ffn", "GCF_002224425v1_20190923.ffn"]
        for filename in filenames:
            frompath = os.path.join(SI.ffn_dir, filename)
            fna_file = filename.split(".ffn")[0] + ".fna"
            topath = os.path.join(SI.fna_dir, fna_file)
            try:
                shutil.copy(frompath, topath)
            except OSError:
                pass

    def test_get_singlecopy_genes():
        singleton_count = SI.get_singleton_genes()
        assert singleton_count == 3

    def test_genenames():
        genes = ["rbsK/rbiA", "rec A", "tarJ'"]
        names = ["rbsK-rbiA", "rec-A", "tarJ"]
        for i, gene in enumerate(genes):
            gene_name = SI.check_genename(gene)
            assert gene_name == names[i]

    def test_write_fasta():
        locustags = SI.get_sequences_from_ffn()
        SI.get_fasta(locustags)
        filename = os.path.join(SI.blast_dir, "singleton_sequences.fas")
        assert os.path.isfile(filename)

    def test_coregene_extract():
        singletonresdir = os.path.join(
                SI.single_dir, "GCF_003254785v1_20190923")
        if os.path.isdir(singletonresdir):
            shutil.rmtree(singletonresdir)
        SI.singleton_seqs = []
        SI.coregene_extract()
        filename = os.path.join(SI.blast_dir, "singleton_sequences.fas")

        assert os.path.isfile(filename)

    def test_run_singleseqs():
        single_dict = SI.run_singleseqs()
        if SI.config.strains:
            ref = ['GCF_003254785v1_btuD_5', 'GCF_003254785v1_group_3360']
        else:
            ref = [
                'GCF_003254785v1_btuD_5', 'GCF_003254785v1_group_3360',
                'GCF_001698165v1_group_2246']
        res = list(single_dict.keys())
        res.sort()
        ref.sort()
        assert res == ref
        return single_dict

    def test_no_results():
        SIQ = SingletonPrimerQualityControl(config, {})
        total_results = SIQ.run_primer_qc()
        assert total_results == []

    prepare_tests()
    test_get_singlecopy_genes()
    test_genenames()
    test_write_fasta()
    test_coregene_extract()
    single_dict = test_run_singleseqs()
    test_no_results()

    from strainprimer import SingletonBlastParser
    SiB = SingletonBlastParser(config)
    status_unique = SiB.run_blastparser(single_dict)
    assert status_unique == 0

    pfile = os.path.join(SiB.results_dir, "primer3_input")
    selected_seqs = []
    with open(pfile) as f:
        for line in f:
            if "SEQUENCE_ID=" in line:
                seq = line.split("=")[1].strip()
                if "group_" in seq:
                    seq = seq.split("group_")[0] + "g" + seq.split("group_")[1]
                selected_seqs.append("Lb_curva_" + seq + "_P2")

    if SiB.config.strains:
        assert len(selected_seqs) == 1
    else:
        assert len(selected_seqs) == 2

    primer_dict = SingletonPrimerDesign(config).run_primerdesign()
    SIQ = SingletonPrimerQualityControl(config, primer_dict)
    infos = SIQ.get_primerinfo(selected_seqs, "mfeprimer")
    assert len(infos[0]) == 5
    total_results = SIQ.run_primer_qc()

    SSu = SingletonSummary(config, total_results)
    SSu.run_summary(mode="last")
    pfile = os.path.join(SSu.summ_dir, "Lb_curva_primer.csv")
    primer = []
    with open(pfile) as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            primer.append(row[0])

    primerref = [
       "Lb_curva_GCF_001698165v1_g2246_P0",
       "Lb_curva_GCF_001698165v1_g2246_P6",
       "Lb_curva_GCF_001698165v1_g2246_P3",
       "Lb_curva_GCF_003254785v1_btuD_5_P0",
       "Lb_curva_GCF_003254785v1_btuD_5_P9",
       "Lb_curva_GCF_001698165v1_g2246_P7"]

    assert primer.sort() == primerref.sort()

    return primer

def test_single_conf():
    os.chdir(BASE_PATH)
    test_start()
    confargs["strains"] = ["GCF_003254785v1"]

    from speciesprimer import CLIconf
    args = AttrDict(confargs)
    nontargetlist = H.create_non_target_list(args.target)
    config = CLIconf(
            args.minsize, args.maxsize, args.mpprimer, args.exception,
            args.target, args.path, args.intermediate,
            args.qc_gene, args.mfold, args.skip_download,
            args.assemblylevel, nontargetlist,
            args.skip_tree, args.nolist, args.offline,
            args.ignore_qc, args.mfethreshold, args.customdb,
            args.blastseqs, args.probe, args.virus, args.genbank,
            args.evalue, args.nuc_identity, args.runmode,
            args.strains, args.subgroup)

    test_skip_pangenome_analysis(config)
    primer = test_Singleton(config)

    primerref = [
       "Lb_curva_GCF_003254785v1_btuD_5_P0",
       "Lb_curva_GCF_003254785v1_btuD_5_P9"]

    assert primer.sort() == primerref.sort()

start = (
    "Create new config files or start pipeline with previously "
    "generated files?\ntype (n)ew or (s)tart:\n")
species = (
        "Please specify target species (comma separated) "
        "or type help for format examples: \n")
path = (
        "Please specify a path to use as the working directory "
        "or hit return to use the current working directory:\n")
targets = (
        "Search for config files for (a)ll or (s)elect targets:\n")

def start_oneinput(prompt):
    prompt_dict = {
        start: "s",
        targets: "s",
        species: "Lactobacillus curvatus",
        path: "/primerdesign/test"
    }
    val = prompt_dict[prompt]
    return val

def test_repeat_run(monkeypatch, config):

    SSu = SingletonSummary(config, [])
    confdir = os.path.join(
        "/", "primerdesign", "test", "Lactobacillus_curvatus", "config")
    testconfig = os.path.join(confdir, "config.json")
    with open(testconfig) as f:
        for line in f:
            confdict = json.loads(line)
    confdict.update({"probe": True})
    confdict.update({"intermediate": False})
    with open(testconfig, "w") as f:
        f.write(json.dumps(confdict))
    monkeypatch.setattr('builtins.input', start_oneinput)
    from speciesprimer import main
    main()

    pfile = os.path.join(SSu.summ_dir, "Lb_curva_primer.csv")
    primer = []
    with open(pfile) as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            primer.append(row[0])

    primerref = [
       "Lb_curva_GCF_003254785v1_btuD_5_P0",
       "Lb_curva_GCF_003254785v1_btuD_5_P9"]

    assert primer.sort() == primerref.sort()


def test_falsestart():
    cmd = [
        "strainprimer.py", "-t", "Lactobacillus_curvatus"]

    outputlist = G.read_shelloutput(cmd)
    
    assert outputlist == [
        "Start this script with speciesprimer.py and the "
        "'--runmode strain' option"]


def test_end(config):
    def remove_test_files(config):
        test = config.path
        shutil.rmtree(test)
        tmp_path = os.path.join("/", "pipeline", "tmp_config.json")
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)
        os.chdir(BASE_PATH)
        assert os.path.isdir(test) is False

    remove_test_files(config)


if __name__ == "__main__":
    print(msg)
