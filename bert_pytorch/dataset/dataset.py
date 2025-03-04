from torch.utils.data import Dataset
import tqdm
import torch
import random


class BERTDataset(Dataset):
    def __init__(self, corpus_path, vocab, seq_len, encoding="utf-8", corpus_lines=None, on_memory=True):
        self.vocab = vocab
        self.seq_len = seq_len

        self.on_memory = on_memory
        self.corpus_lines = corpus_lines
        self.corpus_path = corpus_path
        self.encoding = encoding

        with open(corpus_path, "r", encoding=encoding) as f:
            #读取预料库后分下面2种情况处理：
            if self.corpus_lines is None and not on_memory: #如果不将语料库直接加载到内存，则需先确定语料库行数
                for _ in tqdm.tqdm(f, desc="Loading Dataset", total=corpus_lines):
                    self.corpus_lines += 1

            if on_memory:
                #数据集全部加载到内存，语料库解析成list类型的self.liines属性
                self.lines = [line[:-1].split('\t')
                              for line in tqdm.tqdm(f, desc="Loading Dataset", total=corpus_lines)] #对预料库每行根据\t字符分成2个sentence               
                self.corpus_lines = len(self.lines) #获取语料库行数

        if not on_memory: 
            self.file = open(corpus_path, "r", encoding=encoding)
            self.random_file = open(corpus_path, "r", encoding=encoding)
            #错位抽取负样本，作用是什么?
            for _ in range(random.randint(self.corpus_lines if self.corpus_lines < 1000 else 1000)):
                self.random_file.__next__()

    def __len__(self):
        return self.corpus_lines

    def __getitem__(self, item):
        #魔术方法__getitem__的定义，功能令类的实例对象向list那样根据索引item取值
        #BERTDataset类实例化返回的bert对象均会进行Next Sentence操作和Masked LM操作
        t1, t2, is_next_label = self.random_sent(item) #Next Sentence操作
        t1_random, t1_label = self.random_word(t1) #Masked LM操作, 其中t1_label表示t1各个位置被masked的类别索引，参看vocab.py中Vocab类的初始化定义
        t2_random, t2_label = self.random_word(t2) 

        # [CLS] tag = SOS tag, [SEP] tag = EOS tag
        t1 = [self.vocab.sos_index] + t1_random + [self.vocab.eos_index] #论文Figure2
        t2 = t2_random + [self.vocab.eos_index]

        t1_label = [self.vocab.pad_index] + t1_label + [self.vocab.pad_index]
        t2_label = t2_label + [self.vocab.pad_index]

        segment_label = ([1 for _ in range(len(t1))] + [2 for _ in range(len(t2))])[:self.seq_len]
        bert_input = (t1 + t2)[:self.seq_len]
        bert_label = (t1_label + t2_label)[:self.seq_len]

        padding = [self.vocab.pad_index for _ in range(self.seq_len - len(bert_input))] #最大长度和实际长度之差就是需要padding的位置数量
        bert_input.extend(padding), bert_label.extend(padding), segment_label.extend(padding)

        output = {"bert_input": bert_input,
                  "bert_label": bert_label,
                  "segment_label": segment_label,
                  "is_next": is_next_label}

        return {key: torch.tensor(value) for key, value in output.items()}

    def random_word(self, sentence):
        #sentence转换成sentence中的token在token-index词典中对应的index
        tokens = sentence.split()
        output_label = [] #该列表只存0和非0数字，0表示对应位置的token属于85%没被替换的，非0数字是对应位置的token在被mask处理前的vocab中对应的index

        for i, token in enumerate(tokens):
            prob = random.random()
            #BERT随机选择15%的tokens进行mask
            if prob < 0.15:
                #对于随机选择的15%的tokens，再做一次随机
                prob /= 0.15

                # 80% randomly change token to mask token
                if prob < 0.8:
                    tokens[i] = self.vocab.mask_index

                # 10% randomly change token to random token
                elif prob < 0.9:
                    tokens[i] = random.randrange(len(self.vocab))

                # 10% doesn't change current token
                else:
                    tokens[i] = self.vocab.stoi.get(token, self.vocab.unk_index)

                output_label.append(self.vocab.stoi.get(token, self.vocab.unk_index))

            else:
                tokens[i] = self.vocab.stoi.get(token, self.vocab.unk_index) #未被masked的词，用其在vocab中真正的index填充
                #具体地，self.vocab.unk_index=1，上句相当于从stoi token-index字典
                output_label.append(0)

        return tokens, output_label

    def random_sent(self, index):
        t1, t2 = self.get_corpus_line(index)        
        # for sentence A and B, 50% of the time B is the actual next sentence that follows A(labeled as NotNext)
        # and for 50% of the time it is a random sentence from the corpus(labeled as NotNext)
        if random.random() > 0.5:
            return t1, t2, 1 #1表示isNext
        else:
            return t1, self.get_random_line(), 0 #0表示isNotNext

    def get_corpus_line(self, item):
        if self.on_memory:
            return self.lines[item][0], self.lines[item][1]
        else:
            line = self.file.__next__()
            if line is None:
                self.file.close()
                self.file = open(self.corpus_path, "r", encoding=self.encoding)
                line = self.file.__next__()

            t1, t2 = line[:-1].split("\t")
            return t1, t2

    def get_random_line(self):
        if self.on_memory:
            return self.lines[random.randrange(len(self.lines))][1]

        line = self.file.__next__()
        if line is None:
            self.file.close()
            self.file = open(self.corpus_path, "r", encoding=self.encoding)
            for _ in range(random.randint(self.corpus_lines if self.corpus_lines < 1000 else 1000)):
                self.random_file.__next__()
            line = self.random_file.__next__()
        return line[:-1].split("\t")[1]